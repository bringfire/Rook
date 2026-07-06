# Director Short-Ref Storage Cutover Design

Date: 2026-07-06
Status: approved for user review

## Purpose

Pearson Director actor metadata currently uses semantic IDs as physical folder
and file names under `.rook/director_planning/...`. That layout is portable as
relative metadata, but it is not transfer-durable: deep destination roots can
push valid Director metadata paths into Windows path-length failures.

This design defines a Director-only canonical short-ref storage protocol for
actor metadata. The goal is to preserve semantic actor/grouping decisions while
removing semantic labels from physical path segments.

## Scope

This pass implements the Director actor-metadata cutover first:

- ActorSet metadata.
- Actor subset metadata.
- ActorGrouping/band-set metadata.
- SelectionSnapshot metadata.
- Migration report metadata.
- Checked-in Canvas Director fixtures that bind to those refs.

Director frame/video run outputs remain out of scope because their current
physical paths are already shallow/static enough for this failure mode, and they
do not use semantic actor/grouping IDs as nested filenames. If later Director
outputs introduce semantic-ref storage, they must use the same canonical
short-ref helper.

This is not a repo-wide `.rook` policy rewrite.

## Storage Contract

Canonical writes use only typed shallow folders:

```text
.rook/director/v2/actor_sets/as_<12hex>.json
.rook/director/v2/subsets/sub_<12hex>.json
.rook/director/v2/groupings/grp_<12hex>.json
.rook/director/v2/snapshots/snap_<12hex>.json
.rook/director/v2/migration_reports/mig_<hash>.json
```

Legacy files under `.rook/director_planning/...` remain untouched. They are
read-only transition inputs and comparison evidence.

Read contract:

```text
.rook/director/v2/...          accepted as canonical
.rook/director_planning/...    accepted as explicit legacy
```

Write contract:

```text
.rook/director/v2/...          only
.rook/director_planning/...    never
```

"Parallel canonical cutover" means migration creates the canonical tree beside
the legacy evidence tree. It does not mean dual-writing during normal metadata
generation.

All new Director actor-metadata ref generation must go through one shared
storage-ref helper. Callers must not concatenate `.rook/...` metadata paths
manually.

## Storage Identity

The storage-ref helper builds a canonical identity object, serializes it as:

```python
json.dumps(
    identity,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")
```

It hashes those bytes with SHA-256, truncates to 12 hex chars, and applies a
typed prefix.

Identity inputs:

```text
actor set:
  { "kind": "actor_set", "actor_set_id": "..." }

selection snapshot:
  { "kind": "selection_snapshot", "snapshot_id": "..." }

subset:
  { "kind": "subset", "actor_set_id": "...", "subset_id": "..." }

grouping:
  { "kind": "grouping", "actor_set_id": "...", "subset_id": "...", "band_set_id": "..." }
```

Generated refs:

```text
.rook/director/v2/actor_sets/as_<hash>.json
.rook/director/v2/snapshots/snap_<hash>.json
.rook/director/v2/subsets/sub_<hash>.json
.rook/director/v2/groupings/grp_<hash>.json
```

Each canonical file includes:

```json
{
  "schema_version": 2,
  "storage_version": 2,
  "ref_protocol": "director_short_refs_v1",
  "storage_identity": {
    "kind": "grouping",
    "actor_set_id": "...",
    "subset_id": "...",
    "band_set_id": "..."
  }
}
```

Semantic IDs remain inside the metadata JSON. They must not appear in canonical
path segments.

If a canonical destination exists, normal canonical writers compare the stored
`storage_identity` against the computed identity:

- `created`: destination did not exist and was written.
- `updated`: destination existed with the same `storage_identity` and was
  atomically replaced with the new canonical payload.
- `conflicted`: destination existed with a different `storage_identity`.

This keeps refs stable across ordinary content edits. Conflicts are hard errors.
Normal writers must not overwrite files whose stored `storage_identity` differs
from the computed identity.

## Reader Behavior

Runtime readers accept two explicit storage protocols.

Canonical refs:

- ref starts with `.rook/director/v2/`;
- `schema_version == 2`;
- `storage_version == 2`;
- `ref_protocol == "director_short_refs_v1"`;
- `storage_identity` exists;
- `storage_identity -> expected ref` matches the requested ref;
- requested ref resolves to the same expected ref.

Legacy refs:

- ref starts with `.rook/director_planning/`;
- `schema_version == 2`;
- no storage marker is required;
- load results surface `legacy_ref: true`;
- load results surface `storage_protocol: "legacy_director_planning_v2"`.

Canonical load results surface:

```json
{
  "legacy_ref": false,
  "storage_protocol": "director_short_refs_v1"
}
```

Legacy acceptance is a named compatibility branch, not accidental behavior from
a permissive path validator. The implementation should include a clear
deprecation note for later removal after canonical Pearson workflows are
validated.

## Migration Behavior

Migration writes a canonical short-ref tree from legacy Director actor metadata.
It never edits or deletes the legacy tree.

Migration is deterministic and idempotent. Rerunning it against the same inputs
produces the same refs and a report whose entries show `reused` for unchanged
canonical files.

The migration follows only known Director actor metadata link fields, such as:

- `source_snapshot_ref`;
- `source_occurrence_snapshot_ref`;
- `subsets[].ref`;
- `acceptance.accepted_selection_snapshot_ref`;
- `band_sets[].ref`;
- `exemplar_selection_snapshot_ref`.

It must not perform arbitrary string replacement across JSON.

The migration report is required output. It is returned by the migration API and
may also be written under canonical storage. The persisted report ref must be
deterministic and stable across idempotent reruns. It is derived from migration
input identity or from sorted `old_ref -> new_ref` mappings excluding run
status. Per-entry status may change from `created` to `reused` across reruns
without changing the report ref:

```text
.rook/director/v2/migration_reports/mig_<hash>.json
```

Each mapping entry records:

```json
{
  "old_ref": ".rook/director_planning/...",
  "new_ref": ".rook/director/v2/...",
  "metadata_kind": "director_actor_grouping",
  "semantic_id": "same_orientation_mullions_001_bands_001",
  "status": "created"
}
```

For migration, an existing canonical destination is:

- `created`: destination did not exist and was written.
- `reused`: destination existed with the same `storage_identity` and equivalent
  canonical payload.
- `conflicted`: destination existed with a different `storage_identity` or
  non-equivalent canonical payload.

If any entry is `conflicted`, migration fails overall and includes the
conflicted entry in the report. A future implementation may add an explicit
overwrite flag, but the default migration behavior is no overwrite.

## Fixtures And Canvas Boundary

Checked-in Canvas Director fixtures and tests should move to canonical refs in
the same implementation work. `pearson_v2_smoke.json` should bind to
`.rook/director/v2/...` refs after migration.

Live Grasshopper canvas panel mutation is out of scope. Existing open canvases
that still point to legacy refs continue to work through explicit legacy-read
support during this transition. Updating live panels is a separate manual
validation step or future tool.

## Path Budget

New canonical generated refs must satisfy both invariants:

- project-relative ref length is at most 120 characters;
- no path segment contains actor set IDs, subset IDs, band set IDs, snapshot IDs,
  or other semantic labels.

Automated tests should also verify representative transfer headroom without
requiring an external drive:

```text
len(str(deep_destination_root / relative_ref)) < 240
```

The deep destination root should be deterministic and representative of common
transfer paths. Manual Pearson validation may additionally copy the project to a
real transfer target, but that is not a unit-test gate.

Path-budget enforcement applies to generated canonical refs. It must not block
loading legacy refs.

## Tests

Focused tests should cover:

- Fixed hash vectors: known identity inputs produce exact refs.
- Writer output: `write_actor_metadata_bundle_v2` emits only
  `.rook/director/v2/...` refs.
- Writer regression: no production writer emits `.rook/director_planning/...`.
- No semantic path leakage in canonical refs.
- Project-relative path budget and representative deep-root budget.
- Canonical load requires `storage_version`, `ref_protocol`, and matching
  `storage_identity`.
- Wrong-file detection rejects a canonical payload copied under the wrong short
  filename.
- Legacy load accepts `.rook/director_planning/...` only through the explicit
  legacy branch and returns `legacy_ref: true`.
- Migration rewrites known link fields to canonical refs.
- Migration preserves semantic fields.
- Migration emits the required mapping report.
- Migration reruns produce `reused`.
- Migration conflicts fail overall with a conflicted report entry.
- Checked-in fixtures use `.rook/director/v2/...`, except tests intentionally
  exercising legacy reads.

## Pearson Validation

Manual Pearson validation should:

1. Run migration on Pearson `.rook/director_planning/...` actor metadata.
2. Confirm the old tree is untouched.
3. Confirm `.rook/director/v2/...` contains actor sets, subsets, groupings,
   snapshots, and a migration report.
4. Update checked-in Pearson fixture refs to canonical refs.
5. Run focused Python tests.
6. Optionally copy the project to a real transfer target and verify the
   canonical tree stays below path-budget expectations.

## Acceptance

This design is implemented when:

- new Director actor metadata writes only canonical short refs;
- canonical files include storage markers and `storage_identity`;
- legacy actor metadata remains readable with explicit diagnostics;
- migration creates a canonical tree without mutating legacy files;
- migration emits a required mapping report;
- checked-in Pearson/Canvas Director fixtures use canonical refs;
- tests prove hash stability, path budget, no semantic path leakage, legacy
  read diagnostics, migration idempotency, and conflict handling.
