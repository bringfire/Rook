# Director v2 Relative Actor Metadata Design

Date: 2026-07-02
Status: ready for user review
Branch: `codex/director-relative-metadata-paths`

## Purpose

Director actor metadata currently stores prototype absolute filesystem paths in
its durable JSON. That makes accepted actor/grouping metadata tied to the
machine and drive where it was created, even though the intended project shape is
portable: a `.3dm` file with a sibling `.rook/` metadata folder.

This design defines the first strict runtime contract for Director actor
metadata pathing:

```text
active .3dm directory
  .rook/
    ...
```

ActorSet, ActorGrouping, and referenced SelectionSnapshot metadata move to
`schema_version: 2`. Durable links become `.rook/`-scoped project-relative refs.
Absolute filesystem paths are no longer persisted as identity.

The change is intentionally about path protocol and metadata generation. It does
not redesign actor concepts, grouping concepts, classifier semantics, or the
broader Director intent ledger.

## Scope

In scope:

- v2 runtime metadata contract for ActorSet JSON.
- v2 runtime metadata contract for ActorGrouping/subset/band-set JSON.
- v2 runtime metadata contract for referenced SelectionSnapshot JSON.
- v2 source-occurrence capture for the top-level selected object/context that
  seeds an actor set.
- generator/writer changes so newly generated metadata is v2 by construction.
- a shared resolver contract for `.rook/...` refs.
- explicit one-time v1-to-v2 conversion for current Pearson prototype metadata.
- clean-generation validation in
  `H:\AI EXPERIMENTS\Pearson\ANIMATION\V2`, which starts with no `.rook`
  directory.

Out of scope:

- `animation_intent.json` top-level ledger schema cleanup.
- carrying Director take manifests forward as runtime metadata.
- full-model capture indexes, depth-test metadata, and other broader prototype
  archive files.
- runtime compatibility fallback for v1 absolute-path metadata.
- automatic semantic regrouping or classifier reruns.
- hardening the copied Grasshopper definition as a product contract.

## Design Principles

The product fix is the generation and resolution protocol. Pearson conversion is
acceptance evidence, not the architecture.

The Grasshopper canvas is a disposable proving artifact. Its behavior can inform
the implementation, but its filenames, component layout, folder taxonomy, and
any embedded defaults must not become the contract.

The accepted grouping data is durable semantic payload. Preserve actor IDs,
memberships, grouping order, classifier/provenance, thresholds, representative
selection context, summaries, and user-accepted decisions. Do not regenerate
those decisions unless explicitly starting a new capture.

## v2 Ref Contract

Every v2 runtime metadata document must carry an explicit metadata-kind
discriminator. Readers must use this discriminator, not filename or folder
shape, to confirm that a resolved ref points to the expected kind.

Required kind values:

| Metadata document | Required field |
|---|---|
| ActorSet | `"metadata_kind": "director_actor_set"` |
| Actor subset/intermediate grouping file | `"metadata_kind": "director_actor_subset"` |
| ActorGrouping/band-set file | `"metadata_kind": "director_actor_grouping"` |
| SelectionSnapshot | `"metadata_kind": "director_selection_snapshot"` |

All durable metadata refs in v2:

- are strings;
- start with `.rook/`;
- use forward slashes;
- are relative, not absolute;
- contain no empty path segments;
- contain no `.` or `..` path segments;
- do not contain a Windows drive prefix;
- do not contain UNC prefixes;
- resolve under the active `.3dm` directory;
- resolve to the expected metadata kind when loaded.

The resolver base is only the directory of `RhinoDoc.ActiveDoc.Path`.

The resolver must not fall back to:

- the `.gh` file directory;
- the process current working directory;
- the MCP server working directory;
- the repository root;
- the old absolute path embedded in v1 metadata.

If the active Rhino document is unsaved or has no usable file path, v2 generation
and v2 ref resolution fail with a clear error such as
`document_path_required`.

## Runtime Path Fields

Durable identity uses `*_ref`, not `*_path`.

Runtime tools may compute absolute paths for diagnostics or convenience, but
those fields must be named as resolved runtime data, for example:

```json
{
  "actor_set_ref": ".rook/director_planning/actor_sets/example.json",
  "resolved_actor_set_path": "H:\\AI EXPERIMENTS\\Pearson\\ANIMATION\\V2\\.rook\\director_planning\\actor_sets\\example.json"
}
```

`resolved_*_path` fields are ephemeral runtime outputs. They are not durable
identity and must not be required to load v2 metadata.

Scoped no-absolute-path checks apply to durable identity fields and durable
metadata refs. Runtime diagnostics may include resolved absolute paths if they
are clearly named `resolved_*_path`.

## Source Document Identity

v2 metadata must not store the active Rhino file as an absolute `model_path` or
`document.path`.

Instead, v2 source document metadata should be informational and portable:

```json
{
  "source_document": {
    "file_name": "Axon_Pearson_Experimental_TESTING.3dm",
    "model_guid": "optional-if-available",
    "content_hash": "optional-if-computed",
    "captured_at": "2026-07-02T00:00:00Z"
  }
}
```

The exact available document identity fields depend on the current generator
surface. `file_name` is the minimum required field. A model GUID and content hash
are useful if available, but neither should block the pathing protocol.

The active `.3dm` directory remains the resolver base. `source_document.file_name`
is provenance, not a path resolver.

## v1 to v2 Field Rename Map

The migration must use an explicit field map. Do not preserve old absolute
durable path fields by accident.

ActorSet:

| v1 field | v2 field | Rule |
|---|---|---|
| `schema_version: 1` | `schema_version: 2` | Required version bump. |
| absent | `metadata_kind: "director_actor_set"` | Required discriminator. |
| `model_path` | `source_document.file_name` plus optional model identity | Do not store absolute model path. |
| `source_snapshot_path` | `source_snapshot_ref` | Convert to `.rook/...` ref. |
| `subsets[].path` | `subsets[].ref` | Convert to `.rook/...` ref. |

Actor subset / grouping intermediate metadata:

| v1 field | v2 field | Rule |
|---|---|---|
| `schema_version: 1` | `schema_version: 2` | Required version bump. |
| absent | `metadata_kind: "director_actor_subset"` | Required discriminator. |
| `acceptance.accepted_selection_snapshot_path` | `acceptance.accepted_selection_snapshot_ref` | Convert to `.rook/...` ref. |
| `band_sets[].path` | `band_sets[].ref` | Convert to `.rook/...` ref. |

ActorGrouping / band-set metadata:

| v1 field | v2 field | Rule |
|---|---|---|
| `schema_version: 1` | `schema_version: 2` | Required version bump. |
| absent | `metadata_kind: "director_actor_grouping"` | Required discriminator. |
| `exemplar_selection_snapshot_path` | `exemplar_selection_snapshot_ref` | Convert to `.rook/...` ref. |

SelectionSnapshot:

| v1 field | v2 field | Rule |
|---|---|---|
| `schema_version: 1` | `schema_version: 2` | Required version bump. |
| absent | `metadata_kind: "director_selection_snapshot"` | Required discriminator. |
| `model_path` | `source_document.file_name` plus optional model identity | Do not store absolute model path. |
| `document.path` | `source_document.file_name` plus optional model identity | Remove absolute path. Preserve other document facts if useful. |

`animation_intent.json`:

- out of scope for this branch;
- existing `snapshot_path` fields remain ledger prototype data for now;
- future work should define a separate ledger-level schema and migration.

## Generation First

New metadata generation must produce v2 from the start. The generator/writer is
the source of truth for the new protocol.

Required generation behavior:

- create `.rook/` under the active `.3dm` directory if needed;
- capture the source occurrence/top-level authoring context through a v2 tool,
  not by copying or hand-editing prototype take JSON;
- write ActorSet, ActorGrouping/subset/band-set, and SelectionSnapshot metadata
  with `schema_version: 2`;
- write the required `metadata_kind` discriminator for every generated metadata
  file;
- emit durable links as `.rook/...` refs;
- never write `model_path`, `document.path`, `source_snapshot_path`,
  `subsets[].path`, `band_sets[].path`, or
  `exemplar_selection_snapshot_path` as durable identity;
- validate all refs before writing the final JSON;
- fail if the active document is unsaved.

## Source Occurrence Capture

The old prototype take archive captured source occurrence context that the
actor metadata writer/reader alone does not replace. The v2 pathing contract is
not complete until this capture path is converted too.

The production source-occurrence capture entry point is:

```text
rhino_director_capture_source_occurrence_v2
```

Required behavior:

- resolve the project root from the active saved `.3dm`;
- accept either the current Rhino selection or explicit object IDs;
- require top-level selected document objects;
- capture selected object identity, type, layer, visibility, bbox, and block
  instance facts when the object is an `InstanceReference`;
- capture block definition identity, instance identity, insertion/scale/transform
  facts available from the live routes, direct definition inventory, and nested
  instance inventory where available;
- write a v2 `director_selection_snapshot` under `.rook/`;
- return only durable `.rook/...` refs plus clearly named runtime diagnostics;
- never write `director_takes`;
- never persist drive-root or UNC absolute paths as durable identity.

Prototype `.rook/director_takes/**` files are temporary reference material only.
They are not runtime metadata, are not a v2 compatibility surface, and must not
be required after the v2 capture tool is validated.

The copied `animation test.gh` in the V2 folder is a behavioral reference only
until the components/templates are updated or regenerated. Clean-generation
acceptance must not depend on hardcoded original
`H:\AI EXPERIMENTS\Pearson\ANIMATION\.rook` paths.

## Runtime Reader Behavior

Runtime readers/components are strict:

- accept `schema_version: 2` metadata only;
- require the expected `metadata_kind` value for each loaded document;
- reject `schema_version: 1` actor metadata with a clear migration-required
  error such as `metadata_schema_unsupported`;
- reject v2 metadata that contains old absolute durable fields;
- reject invalid refs before reading target files;
- load target files only after ref validation and expected-kind checks.

There is no runtime auto-repair and no transparent v1 compatibility branch.

## Migration

The migration is explicit and offline. It is allowed to convert curated prototype
v1 metadata, but it is not part of normal runtime loading.

Migration behavior:

- read v1 ActorSet, ActorGrouping/subset/band-set, and referenced
  SelectionSnapshot JSON;
- validate every absolute path being converted is under the project root;
- convert path fields according to the field map;
- bump converted metadata to `schema_version: 2`;
- add the required `metadata_kind` discriminator;
- preserve curated IDs, object GUIDs, memberships, ordering, classifier
  settings, thresholds, representative context, provenance, summaries, and
  accepted decisions;
- fail if any referenced object ID cannot be reconciled when object validation is
  requested;
- write a report summarizing converted files and any rejected fields.

The migration may preserve original v1 files as backup or write v2 copies,
depending on the implementation plan, but runtime code must not rely on v1.

## Recapture Fallback

Recapture is acceptable if conversion exposes drift. Regeneration is different
and should not be confused with recapture.

Recapture means reading the current active `.3dm` state and writing fresh v2
metadata while preserving the accepted actor/grouping concepts where possible.

Regeneration means rerunning grouping/classifier logic and accepting a new
semantic result. That is out of scope unless explicitly requested.

If object GUIDs from v1 cannot be resolved in the copied or original model, the
implementation should stop and require an explicit reconciliation decision. It
must not silently remap by name, layer, or geometry similarity in this branch.

## Validation Lanes

### Lane A: Clean v2 Generation

Fixture:

```text
H:\AI EXPERIMENTS\Pearson\ANIMATION\V2
  Axon_Pearson_Experimental_TESTING.3dm
  animation test.gh
  # no .rook at start
```

Acceptance:

- starting from no `.rook`, the production actor metadata writer entry point
  used by the updated Director component/template creates v2 actor metadata from
  the active V2 `.3dm` and a minimal known actor-authoring input: the source
  occurrence capture, the roof-uplift actor set target, the same-orientation
  mullion subset, and the accepted band grouping used by the prototype;
- the source occurrence/top-level context is generated by
  `rhino_director_capture_source_occurrence_v2`, not by copied take manifests or
  hand-authored JSON;
- the implementation plan must name this production writer entry point before
  implementation starts;
- the Lane A flow is not satisfied by manually copying or migrating actor
  metadata into V2 before generation, or by a test-only/ad hoc JSON writer that
  is not the production generation path;
- generated ActorSet, ActorGrouping/subset/band-set, and referenced
  SelectionSnapshot files use `schema_version: 2`;
- generated ActorSet, actor subset, ActorGrouping, and SelectionSnapshot files
  carry the expected `metadata_kind` values;
- durable refs are `.rook/...` refs and validate against the v2 ref contract;
- no generated durable identity field contains a drive-root or UNC absolute
  path;
- resolved runtime path outputs, if present, are named `resolved_*_path`.

Lane A is the product gate.

### Lane B: Explicit v1-to-v2 Conversion

Fixture:

```text
H:\AI EXPERIMENTS\Pearson\ANIMATION
  .rook\director_planning\...
```

Acceptance:

- curated v1 Pearson actor metadata converts to v2 without semantic loss;
- the converted JSON follows the explicit field rename map;
- memberships, grouping order, classifier/provenance, thresholds,
  representatives, summaries, and object IDs match the v1 source;
- conversion reports all changed fields;
- no runtime reader is needed to load v1 directly.

Lane B is preservation evidence.

## Tests

Focused tests should cover:

- valid `.rook/...` refs resolve under a supplied model directory;
- resolved refs fail expected-kind validation when the loaded JSON has the wrong
  or missing `metadata_kind`;
- absolute paths, drive prefixes, UNC paths, backslashes, `..`, `.`, empty
  segments, and non-`.rook/` refs are rejected;
- unsaved-document generation fails before writing files;
- v2 source-occurrence capture writes a `director_selection_snapshot` and no
  `director_takes` archive;
- v2 generator emits the new field names and omits old durable `*_path` fields;
- v1 migration converts every field in the rename map;
- v1 migration fails when an absolute path points outside the project root;
- migrated semantic fields are unchanged;
- runtime reader rejects `schema_version: 1`;
- runtime reader rejects v2 JSON that still contains old durable absolute path
  fields.

Live/manual validation should use Lane A and Lane B as described above.

## Non-Goals

This branch does not:

- define the future `animation_intent.json` ledger schema;
- migrate or preserve Director take archives or full-model capture indexes as
  runtime metadata;
- establish a final canonical `.rook/director/...` folder taxonomy;
- add v1 runtime fallback;
- rerun classifier/grouping logic as part of migration;
- make the copied Grasshopper definition a contract artifact.

## Acceptance

The branch is complete when:

- the v2 path protocol is implemented in the metadata writer and resolver;
- source-occurrence capture is implemented as a v2 tool and no longer depends on
  prototype `director_takes`;
- runtime readers reject v1 actor metadata clearly;
- Lane A creates clean v2 actor metadata in the V2 folder from no `.rook`;
- Lane B converts the curated Pearson prototype metadata without semantic loss;
- tests prove the resolver, generator field names, and migration field map;
- no durable v2 actor metadata identity field depends on the original absolute
  `H:\AI EXPERIMENTS\Pearson\ANIMATION` root or any other drive-root or UNC
  absolute path.
