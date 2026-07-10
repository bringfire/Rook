# Rook Three.js Render Scene Compiler Design

## Purpose

Design a Rook workflow that prepares a Rhino model for efficient Three.js
delivery without making the user reason about export internals, draw-call
batching, or synchronization ownership.

The user edits the authoritative Rhino model and deliberately invokes **Update
Render Scene** when ready to preview. Rook synchronizes a persistent derived
Rhino render scene, applies an evidence-backed optimization profile, publishes
an optimized Three.js scene package, validates it, and refreshes the browser
preview. The authoring model is never mutated by this workflow.

## Existing Rook Substrate

This design builds on capabilities already present in Rook:

- native Rhino object, render-mesh, block, layer, and material access;
- layer creation, movement, merging, visibility, locking, and convention tools;
- material inventory, creation, assignment, and purge tools;
- a Rook-owned GLB writer and validator in the mesh2splat pipeline;
- artifact registration and bounded filesystem-safety patterns;
- Director actor IDs, actor sets, pivots, motion packages, and stable metadata;
- worker/snapshot patterns for preparing derived Rhino documents; and
- the isolated Three.js Rhino stress harness, which proves deterministic GLB
  loading, actor metadata survival, absolute-time animation, static-context
  merging, coordinate comparison, browser CPU/GPU measurement, and lifecycle
  handling.

The existing mesh2splat GLB contract remains purpose-specific. The Three.js
scene compiler defines a separate standards-oriented package contract rather
than silently expanding mesh2splat behavior.

## Product Decision

Use a **manifest-first hybrid compiler**.

The derived `.3dm` is a durable, inspectable Rhino render scene. A canonical
manifest bridges Rhino semantics and Three.js runtime structures. Static
optimizations are baked into the GLB where practical; the manifest instructs
the Rook Three.js runtime how to construct ordinary `Mesh`, `InstancedMesh`,
and `BatchedMesh` representations while preserving actor identity.

The primary user actions are:

1. **Create Render Scene** on first use.
2. **Update Render Scene** after a deliberate editing interval.

Updates never run automatically on save. A source change marks the render scene
as stale, but the user controls when synchronization, compilation, and preview
refresh occur.

## Alternatives Considered

### Rhino-document-first

Make layers, blocks, joined meshes, and materials in the derived `.3dm` the
complete export contract. This is easy to inspect, but Rhino structures cannot
fully express Three.js batching, package-specific actor lookup, or runtime
assembly. Export behavior would depend too strongly on document organization.

### Three.js-runtime-first

Export a mostly raw GLB and optimize it entirely in the browser. This enables
fast experimentation, but large scenes pay unnecessary transfer and startup
costs, and the derived Rhino render scene no longer represents the compiled
deliverable.

### Bidirectional general synchronization

Merge arbitrary geometry edits from both the authoring and render documents.
This creates a large conflict-resolution subsystem and weakens the simple user
contract. The authoring model remains authoritative for geometry.

## Architecture

One versioned scene link connects:

```text
Authoring .3dm
  -> synchronized render .3dm
  -> canonical scene manifest
  -> optimized GLB
  -> Three.js runtime assembly
  -> validation, evidence, and browser preview
```

The architecture has six bounded components.

1. **Source snapshot capture** records stable identity, geometry, transforms,
   hierarchy, layers, blocks, materials, pivots, render meshes, and Director
   metadata.
2. **Render-scene synchronizer** creates or updates the derived `.3dm` while
   preserving registered render-only content and overrides.
3. **Semantic auditor** applies conventions and classifies every exportable
   object.
4. **Scene compiler** applies the selected optimization profile and builds the
   canonical manifest plus package inputs.
5. **Package writer and validator** produce and verify the GLB, manifest, and
   compilation report in an isolated run directory.
6. **Preview runtime** loads the package, assembles Three.js runtime objects,
   validates browser behavior, and atomically swaps the visible scene.

These components communicate through versioned plain-data contracts and are
independently testable.

## Slice 1 Runtime And Process Ownership

Slice 1 explicitly requires the Rook MCP Python process. It does not introduce
a separately bundled compiler worker or a plugin-only toolbar command. Create
and Update are exposed as Python MCP tools and are unavailable when the MCP
process is not running. The current derived document and last published preview
remain inspectable without MCP.

| Component | Process and entry point | Threading and cancellation | Durable state and availability |
|---|---|---|---|
| Transaction orchestrator | Rook MCP Python process; new `rook_create_render_scene` and `rook_update_render_scene` tools | Owns the run ID and cancellation token. Awaits every native and managed phase and checks cancellation between them. | Sole writer of `scene-link.json`, `current.json`, `promotion.json`, run manifests, and publication backups. Requires the MCP process for the full operation. |
| Source snapshot capture | RookNative C++ plugin; new native HTTP route called through `bridge.py` | The HTTP handler dispatches every Rhino SDK access through `CMainThreadDispatcher`. Native capture is divided into bounded phases and observes the run cancellation state between phases; an individual Rhino SDK call is not interrupted mid-call. | Writes no scene-link state. Requires a live discovered native instance and a saved active source document. |
| Render-scene synchronizer | RookNative C++ plugin; new native HTTP route called through `bridge.py` | Rhino document reads and mutations run on the Rhino main thread. Candidate serialization may continue off-thread only after all Rhino-owned data has been copied into owned OpenNURBS values. | Produces only the candidate `.3dm` named by the orchestrator. It never promotes the persistent derived document or advances pointers. |
| Render-customization staging | Python MCP actions call a new RookNative route for the active derived document | Native validates the canonical derived path and base run, then applies the draft registry and object markers together on the Rhino main thread in one undo record. | Changes only the in-memory working derived document and marks it modified/stale. It never writes publication files or saves the document. |
| Semantic auditor and scene compiler | Rook MCP Python process; a new production `rook.threejs_scene` package | CPU work runs outside the MCP event loop through a bounded executor and checks cancellation between objects and buckets. | Reads the captured contract, immutable profile descriptor, and execution envelope; writes only the attempt run directory. |
| GLB, manifest, and report writer/validator | Rook MCP Python process; production modules under `rook.threejs_scene` | Runs outside the event loop and checks cancellation between buffer/material stages. It may reuse proven low-level GLB framing helpers, but does not broaden the mesh2splat package contract. | Writes only attempt-owned files until the orchestrator promotes them. |
| Preview host and Three.js runtime | Managed Rook companion `RookWebSurface`, loaded on demand through native P/Invoke callbacks; native HTTP routes remain the only public bridge | Host creation and WebView2 interaction run on the Rhino/managed UI thread; Three.js assembly runs in the WebView. Candidate operations are keyed by run ID and support `prepare`, `commit`, `discard`, `restore`, and `restoreEmpty` commands. | Holds only prepared/visible in-memory preview state and emits run-ID/hash evidence through the managed callback status consumed via a native route. It never writes durable scene-link state. |

The Python orchestrator owns cancellation and durable truth. Native and managed
components must reject stale run IDs and cannot independently promote a run.
Slice 1 success requires all three runtimes: MCP Python, the discovered native
plugin, and the managed WebView2 surface with working WebGL. The hardened
minimal HTML fallback is diagnostic only and cannot satisfy preview acceptance.
If the companion, WebView2, or WebGL is unavailable, compilation may preserve
diagnostic artifacts in the immutable run directory, but the transaction does
not promote.

## Project Layout And Artifact Model

The first Create Render Scene operation allocates a stable `sceneId` and asks
the user to choose the derived `.3dm` path. The default is a sibling file named
`<source-stem>.render.3dm`. Rook stores project bookkeeping under:

```text
.rook/render-scenes/<sceneId>/
  scene-link.json
  current.json
  promotion.json
  conflicts/<conflictId>/
    preserved.3dm
    conflict-record.json
  runs/<runId>/
    candidate.render.3dm
    candidate.scene-link.json
    profile-descriptor.json
    execution-envelope.json
    scene.glb
    scene.manifest.json
    compilation-report.json
    preview-prepared-evidence.json
    preview-visible-evidence.json
```

Run directories are immutable after completion. `current.json` is an atomic
pointer to the last successful run. `promotion.json` is a durable promotion
journal that exists only while a validated run is being promoted. The
persistent derived `.3dm` is replaced through a same-directory temporary file
and, when a prior working document exists, a backup. If the process or machine
stops between file replacements, the next Create or Update command uses the
journal and hashes to complete the promotion or restore the prior derived
document before accepting new work.
The validated `candidate.render.3dm` remains in its immutable run directory as
the committed render-document snapshot. The user-facing derived path is a
working copy that normally matches that snapshot but may become explicitly
stale while the user prepares render customizations.

`conflicts/` is retained user data, not attempt-owned staging. Each
`conflict-record.json` stores schema version, `sceneId`, `conflictId`, source
journal/run IDs, reason, original canonical path, retained project-relative
path, byte size, SHA-256, creation time, and acknowledgement/deletion state. The
record and retained bytes are fsynced before the active promotion journal may
refer to them or cleanup may continue.

The scene link records the source binding, derived document path, immutable
profile descriptor and execution-envelope identities, committed customization
records, object mappings, last successful source snapshot, last successful run
ID, and the committed content-artifact hashes defined below. Paths inside the
project root use safe project-relative references. External derived-document
paths require an explicit user selection and are stored as canonical absolute
paths; Rook never infers a writable path outside the project.

Each committed derived document carries document user strings for
`rook.render.scene_id` and `rook.render.published_run_id`. It never embeds a
scene-link, manifest, or derived-document hash. Customization staging and
Update require those stable IDs to match the selected scene's committed link,
which independently records and verifies the derived-document SHA-256.

Unless a field says otherwise, canonical JSON in this design means the RFC
8785 JSON Canonicalization Scheme encoded as UTF-8 without a byte-order mark;
SHA-256 values are lowercase hexadecimal hashes of those exact bytes.

### Acyclic publication hash graph

Publication uses this strict finalization order. Arrows constrain finalization;
the exact hash edges are stated immediately below:

```text
execution envelope
  -> profile descriptor
  -> candidate render document
  -> GLB
  -> scene manifest
  -> compilation report
  -> prepared preview evidence
  -> visible preview evidence
  -> scene-link.json
  -> current.json
```

The candidate render document contains only stable IDs, source/version data,
and committed Rhino bookkeeping. The GLB contains scene data and identity but
no downstream publication hashes. The manifest contains the descriptor,
envelope, derived-document, and GLB hashes. The report contains the manifest
hash. Prepared evidence contains the report hash and every finalized content
hash through the report. Visible evidence contains the prepared-evidence hash
and repeats the run, package, descriptor, and envelope identities needed to
reject a mismatched callback.

Only after visible evidence is finalized does the orchestrator serialize
`candidate.scene-link.json`. It records hashes for the descriptor, envelope,
candidate render document, GLB, manifest, report, prepared evidence, and visible
evidence. It never hashes itself, `current.json`, `promotion.json`, temporary
files, or backups. The orchestrator then computes the scene-link hash and
serializes `current.json` as `{sceneId, runId, sceneLinkSha256}`. No upstream
artifact refers to `current.json` or its hash.

No artifact contains its own SHA-256 unless its schema explicitly defines a
self-hash field whose value is omitted from the canonical hash input. This
omission rule applies to `descriptorSha256`, `executionEnvelopeSha256`, and the
draft registry's `registrySha256`. Preview evidence, the scene link, and the
current pointer do not carry self-hash fields; their hashes live only in later
artifacts or the phase journal.

## Source Binding And Project Root

Slice 1 requires a saved, unmodified source `.3dm`. Create and Update reject an
untitled document or a document for which Rhino reports unsaved changes. The
runtime document serial number is used only to target the active session; it is
never persisted as durable identity.

Create requires an explicit project root. If the source is already beneath a
directory containing `.rook`, that directory is proposed; otherwise the user
must select or initialize a root that contains the source file. The canonical
source path must be inside the canonical project root. Project bookkeeping is
always rooted at that `.rook` directory even when the user explicitly chooses
an external derived-document destination.

Windows paths are canonicalized by resolving them to absolute final targets,
normalizing separators and extended-path prefixes, and removing redundant
segments and trailing separators except at a root. Canonical comparisons are
case-insensitive. A case-only rename therefore retains the binding. Reparse
points and UNC paths are accepted only after final-target resolution proves
that the source remains under the selected project root. The scene link stores
both a user-facing display path and the canonical comparison path.

The durable Slice 1 binding is the canonical saved path, not an invented Rhino
document UUID. Each successful snapshot also stores a source version
fingerprint containing the saved-file SHA-256, byte size, source object-ID-set
SHA-256, and document-settings SHA-256. Content fingerprints are expected to
change during normal editing; they identify the compiled source version and
detect staleness, not the document by themselves. The replacement check is
deterministic: when both the prior and current object censuses are nonempty and
their UUID intersection is empty, Update blocks with
`source_replacement_suspected` rather than silently treating an unrelated
document as a normal edit. A deliberate replace-all workflow must use Relink,
even when the canonical path is unchanged.

The object-ID-set hash covers lowercase canonical UUID strings sorted by
ordinal value and joined with a single LF. The document-settings hash covers a
versioned canonical JSON object containing model units, absolute tolerance,
angle tolerance, relative tolerance, and world basis. Adding a fingerprint
field requires a fingerprint schema-version change.

Save As, a non-case-only rename, or a move changes the binding and requires the
explicit **Relink Render Scene** action. Relink requires a saved candidate under
the same project root, shows path, content-hash, and object-ID continuity
evidence, and updates the binding only after user confirmation. Missing source
paths and active-document/path mismatches block Create or Update.

## Derived Document Working-State Contract

The persistent derived `.3dm` may be opened, inspected, and customized between
transactions. It is never an in-memory promotion target. Before Create,
Update, or promotion recovery begins, the orchestrator asks every discovered
RookNative instance for a Rhino-main-thread enumeration of open document paths;
each check refreshes instance discovery first.
If the canonical derived path is open in any instance, the operation fails
before candidate construction with `derived_document_open`. An open-but-saved
document is still blocking because reopening the same path does not prove that
Rhino reloaded the replaced bytes.

The first Create requires a derived destination that does not already exist.
Update requires the working derived document to be saved and closed. The
orchestrator acquires the ordered lock set below at the optimistic-concurrency
gate, repeats the open-document check immediately before both journal creation
and render replacement, and performs the same-directory replacement itself. A
sharing or replacement failure returns `derived_document_locked` and leaves the
candidate unpromoted. The lock set is held through preview commit, pointer
commit, cleanup, or rollback.

### Lock identities and acquisition order

The primary destination lock is an OS-visible per-user named mutex whose ID is
the SHA-256 of a canonical JSON object with exactly three fields: `contract`
is the literal `derived-path-lock@1`, `projectRoot` is the canonical project-root
string, and `derivedPath` is the canonical derived-path string. It contains no
`sceneId`, run ID, source identity, or process identity. Consequently, two first
Creates that chose the same canonical destination contend on the same lock even
when they allocated different provisional scene IDs.

A secondary scene lock serializes bookkeeping for an existing scene across
Update, Relink, and recovery. Its ID is the SHA-256 of a canonical JSON object
with exactly three fields: `contract` is the literal `render-scene-lock@1`,
`projectRoot` is the canonical project-root string, and `sceneId` is the scene
ID string.
Every operation acquires all required destination locks first in ascending lock
ID order, then all required scene locks in ascending lock ID order, and releases
them in reverse order. A normal Create or Update needs one of each; Relink needs
the old and new destination locks followed by the scene lock. No code may
acquire a destination lock while holding a scene lock. Lock timeout returns
`render_scene_busy` without changing a journal or publication file.

First Create may allocate a provisional `sceneId` and attempt directory before
locking, but it cannot create `promotion.json`, claim the destination, or
publish until it holds the destination lock followed by its scene lock and
passes full base-state revalidation. The losing concurrent Create sees the
destination created by the winner, returns `candidate_base_stale`, and leaves
only cleanup-eligible attempt artifacts.

Replacement success is not sufficient evidence that no Rhino instance loaded
the old bytes during the last-check/replacement window. Immediately after every
forward replacement and before preview commit, the orchestrator refreshes
discovery and again asks all live instances for a main-thread enumeration. Each
matching open document
reports its in-memory `sceneId`, `publishedRunId`, and modified flag rather than
only filesystem-handle state. A document reporting the candidate run loaded the
new bytes and is not stale. A prior, missing, or unknown run marker advances the
journal to `render_open_conflict`. After enumeration, the orchestrator also
rehashes the working path; any value other than the candidate hash produces the
same conflict, including an old document that saved and closed before it could
be enumerated. Preview and pointers remain on the prior run.

Conflict recovery waits for the document to close before restoring the prior
working bytes. If the open document saved unexpected bytes, Rook first moves
them into the scene's retained `conflicts/<conflictId>/preserved.3dm`, writes and
fsyncs `conflict-record.json`, and then records the conflict ID, path, byte size,
and SHA-256 in `promotion.json`. These bytes are retained user data, never
attempt-owned files. Rollback performs the same pre/post replacement
enumerations and disk-hash verification. If a candidate-loaded document appears
inside the rollback window, Rook re-establishes candidate bytes at the working
path, remains in `rollback_waiting_for_close`, and retries rollback only after
that document closes. No preview or pointer commit is allowed while either
conflict phase is active.

Attempt cleanup, run pruning, successful recovery, journal removal, and normal
project maintenance explicitly exclude retained conflicts. **Review Preserved
Conflict** exposes the record and file. **Acknowledge And Keep Conflict** marks
the record acknowledged without enabling automatic deletion. **Delete
Preserved Conflict** is the only deletion path: after explicit confirmation it
revalidates the confined path and recorded hash, deletes the bytes, and retains
a tombstone record with the original hash and deletion time. A hash mismatch
blocks deletion.

Rook does not silently close, reload, or rebind the user's document. After a
successful transaction the user may reopen the path and receives the promoted
bytes. This fail-closed rule avoids a stale Rhino document later overwriting a
newer published scene.

## Update Transaction

**Update Render Scene** performs one transaction:

1. Validate the scene link, source document, closed derived destination,
   profile descriptor, execution envelope, and current render-scene state, and
   persist the complete candidate base-state token defined below.
2. Capture the authoritative source snapshot.
3. Diff it against the last successful snapshot.
4. Produce a candidate derived `.3dm` in the new run directory.
5. Apply semantic preparation and compile the candidate package.
6. Validate the candidate derived document, GLB, manifest, and actor mapping.
7. Ask the preview runtime to `prepare` the candidate offscreen. It loads and
   assembles the candidate, runs visible-output and browser checks without
   replacing the visible scene, then emits evidence containing the run ID and
   package/profile/envelope hashes.
8. Acquire the destination lock followed by the scene lock and revalidate the
   complete base-state token.
9. Execute the journaled promotion protocol below.

The scene link advances only when the derived document, package, report, and
preview evidence all describe the same successful run. Ordinary cancellation
or failure stops future work, removes only attempt-owned temporary files, and
leaves the last known-good run current. Interrupted promotion is a recoverable
journaled state, not a successful or failed compilation result.

### Optimistic-concurrency gate

The candidate base-state token contains:

- `current.json` presence, SHA-256, and run ID;
- `scene-link.json` presence and SHA-256;
- canonical source path, complete saved-file/source-version fingerprint, and
  the requirement that the targeted live source document remains unmodified;
- working derived-document presence, canonical path, byte SHA-256, embedded
  scene/run IDs, and expected stale/current state;
- customization-draft presence, `baseRunId`, `draftId`, revision, and
  `registrySha256`;
- descriptor and execution-envelope SHA-256 values; and
- absence of any pre-existing promotion journal for the scene.

Expensive capture, compilation, validation, and preview preparation run without
the lock set. Immediately afterward, the orchestrator acquires the destination
lock followed by the scene lock, re-enumerates open Rhino documents, and
recaptures every token field from authoritative live state and disk. It also
rechecks the source document's modified flag. Every field must equal the
candidate's base token byte-for-byte before `promotion.json` is created.

Any difference returns `candidate_base_stale`, discards the prepared preview,
and leaves all publication and working files untouched; the candidate cannot be
rebased or reused. Both locks remain held from successful revalidation through
journal creation, render replacement, preview commit, pointer commit, cleanup,
or completed rollback. Thus two candidates built from the same base cannot both
publish: after the first commits, the second fails its destination presence,
current/link hashes, or run ID.

### Journaled promotion protocol

The journal has explicit `prior` and `candidate` records. `prior.runId`, prior
pointer hashes, prior preview evidence, and prior working-document hash/backup
are nullable. For the first Create, `prior` declares `runId: null`, absent
pointer files, `preview: empty`, and `workingDocument: absent`; the selected
derived path must also be absent. For Update, the prior working document may be
either the current published bytes or a saved stale customization draft, and
the journal records which state it is preserving.

Recovery does not depend on an existing scene link. Before resolving a Create
or Update target, the orchestrator scans `.rook/render-scenes/*/promotion.json`
under the selected project root. A first-Create journal contains the `sceneId`,
canonical project root, canonical source binding, canonical derived path, and
candidate run identity needed to recover or safely match a retried Create.

Recovery's initial journal read is discovery-only. Before changing the journal,
working path, preview, pointers, backups, or retained conflicts, the recovery
worker acquires the journal's destination lock and then its scene lock in the
normal order. It rereads the journal under both locks and verifies that its
`sceneId`, canonical project root, canonical derived path, journal phase, and
file hash still match the discovery read. If another recovery already removed
the journal, the later worker returns `already_recovered`; any other mismatch is
`recovery_state_changed` and performs no mutation. OS mutex abandonment after a
process crash transfers ownership only after the new worker acquires both
mutexes in order and completes this reread. Two journals claiming one canonical
destination are reported as `duplicate_destination_journals` and neither is
mutated automatically.

1. Write and fsync `promotion.json` with the complete nullable prior record,
   validated base-state token, candidate run ID, presence flags, and only the
   hashes finalized through prepared preview evidence: descriptor, envelope,
   candidate render document, GLB, manifest, report, and prepared evidence.
   Set visible-evidence, scene-link, and current outputs to explicit `pending`
   states and phase `prepared`.
2. If a prior working document exists, create and verify its same-directory
   backup. Promote the candidate render document and advance the journal to
   `render_promoted`. `current.json` and `scene-link.json` still identify the
   previous run, or remain absent during first Create. Complete the mandatory
   post-replacement open-document check before continuing.
3. Send preview `commit(runId)` and wait for evidence that the candidate is the
   visible scene with the expected run, package, profile, envelope, actor, and
   renderer hashes. Serialize and fsync `preview-visible-evidence.json`, hash
   it, and advance the journal to `preview_evidenced` with that now-final value.
   The journal and any prior render-document backup remain present.
4. Serialize `candidate.scene-link.json` from the finalized hash DAG, fsync and
   hash it, then advance the journal to `link_finalized`. Replace
   `scene-link.json`, verify its hash, and advance to `link_promoted`.
5. Serialize `current.json` with the finalized scene-link hash, fsync its
   expected bytes, and record that expected hash in journal phase
   `current_ready`. Replace `current.json` last as the durable commit point,
   verify it, and advance to `current_promoted`.
6. Only when the render document, scene link, current pointer, and visible
   preview all match the candidate may the orchestrator remove any backup and
   the promotion journal.

A preview prepare or commit failure during a live transaction causes preview
`discard` followed by `restore(previousRunId)` when a prior run exists, or
`restoreEmpty()` for first Create. Rollback restores every previously present
pointer and the exact prior working-document backup. For first Create it
removes a promoted derived document and any candidate pointer only when their
hashes match the journal; pre-existing or unexpected bytes are never deleted.
Journal removal occurs only after restored presence/absence and hashes are
verified. A restored stale customization draft remains stale and available for
the user to retry. No component may report the candidate as current while a
rollback is pending.

If the process or machine stops after the journal is written, the next Create
or Update performs recovery before serving status or accepting new work. It may
complete the candidate only when all candidate artifacts remain valid and the
preview can reproduce matching prepared and committed evidence. Otherwise it
restores the prior working document or its declared absence, prior pointer
files or their absence, and the prior run or empty preview. Recovery is
successful when one run is consistently current, or first Create is
consistently absent, and the journal and obsolete backup are removed; it never
leaves mixed state as an accepted outcome. Any unexpected path occupant or
hash mismatch leaves recovery blocked for explicit user intervention rather
than deleting or overwriting unknown data.

## Synchronization And Ownership Contract

The authoring model is authoritative for:

- geometry and topology;
- object transforms and hierarchy;
- object presence or deletion;
- source layer membership;
- source material assignments when no registered render override is active;
  and
- Director actor identity, actor-set membership, pivots, and authored motion.

The derived render scene owns:

- render cameras;
- lights and environments;
- explicitly registered material overrides; and
- render-only helper objects and layers.

Rook maintains a stable mapping from the source binding and source object UUID
to the corresponding render-scene object and compiled representation. A source
object copy receives a new identity. Director-authored actor IDs remain
authoritative. An object classified as an actor without Director metadata
receives a deterministic ID of the form `rhino_<uuid-without-separators>` and
that ID is persisted in the scene link.

On update:

- new source objects are added;
- changed objects are replaced or updated;
- deleted objects are removed from the render scene and package;
- unchanged objects may reuse prior compiled results when all dependencies are
  unchanged; and
- a changed layer, material, pivot, hierarchy, or geometry signature
  invalidates every affected merge, instance, or batch group.

Direct geometry edits to synchronized objects in the render scene are not a
second source of truth. The next update restores source geometry and reports
that the render-side edit was superseded. The explicit rules below define every
presentation change that Slice 1 preserves or rejects.

### Pending render customization contract

`scene-link.json` is always the last committed publication snapshot. The four
render-customization actions never edit it directly. They operate only on the
open working derived document and stage intent in the document user string
`rook.render.customization_draft` within the same Rhino undo record as their
object markers.

The canonical draft registry contains its schema version, `draftId`,
`baseRunId`, revision, ordered operations, and registry SHA-256. Operations are
`set_override`, `clear_override`, `adopt_render_only`, or
`remove_render_only`; each records the stable target IDs, expected before/after
markers, and any canonical material payload. Clear and remove operations are
explicit tombstones rather than inferred missing markers.

`registrySha256` is the SHA-256 of the canonical draft registry with the
`registrySha256` field itself omitted. Validation rejects a missing hash field,
an unexpected extra field, or a non-canonical operation order.

An action marks the working render scene and preview status stale and leaves
the Rhino document modified; it never saves unrelated edits automatically. The
user saves and closes the derived document before Update. If Rhino exits before
the save, neither the registry nor its markers are durable. After a successful
save they reside in the same `.3dm`; an unreadable file, invalid registry hash,
wrong `baseRunId`, duplicate operation, or registry/marker mismatch is blocking.

Update reads the closed working document, validates the draft against the
current scene link, and applies its operations while constructing the
candidate. The candidate derived document contains the resulting committed
markers but no pending draft registry. The corresponding scene-link model stays
in memory until visible preview evidence is finalized, then
`candidate.scene-link.json` is serialized in the acyclic hash order. Only the
normal journaled promotion publishes them together. If compilation, preview,
or promotion fails, rollback restores the exact saved working document with its
draft, the committed scene link and preview remain on the prior run, and status
remains stale so the user can retry.

### Slice 1 material override contract

Slice 1 preserves a material override only when it was created or adopted with
the explicit **Set Render Material Override** action. That action allocates an
`overrideId`, keys a pending operation to the source object UUID, captures the
complete normalized override material payload and signature in the draft
registry, and marks the corresponding derived object with the user string
`rook.render.material_override_id=<overrideId>`. The override record also
contains its source object UUID, draft ID, material definition ID, and intended
active state. Successful Update writes the committed creation run ID into the
candidate scene link.

The override payload uses the same canonical material fields and texture-byte
hashes defined by the compiler's material-compatibility contract. Its signature
is the SHA-256 of the canonical JSON encoding of that payload. Update
recomputes the signature from the marked derived material before accepting it.

Appearance precedence for a synchronized object is:

1. active registered render material override;
2. source object material assignment;
3. source layer material assignment; and
4. compiler default material.

A later source material change does not silently remove an active override; the
report records both the changed source material and retained override. **Clear
Render Material Override** stages an explicit tombstone and marker removal; a
successful Update removes the committed scene-link record and returns the
object to source-material inheritance. A missing, duplicate, tampered, or
signature-mismatched committed record or pending operation is blocking unless
the exact difference is authorized by a valid draft operation.

### Other render-document edits

- Cameras, lights, and environments in the derived document are render-owned
  and preserved.
- Other render-only objects or layers are preserved only when registered by
  Rook through a pending adopt operation with the user string
  `rook.render_only=true`; their stable render-only IDs enter the scene link
  only on successful Update. Removal likewise requires an explicit tombstone.
- Saved, unregistered changes to geometry, transform, hierarchy, name, layer,
  visibility, or material on a source-mapped object are overwritten from the
  source with an explicit warning. They are not promoted to overrides.
- Unsaved derived-document changes block Update.
- Duplicate or altered source-mapping markers, deletion or mutation of
  Rook-owned bookkeeping layers, missing registered render-only objects, and
  unresolvable override materials block Update as integrity failures unless a
  valid draft operation authorizes the exact transition.

These rules let routine source edits synchronize without a conflict dialog
while ensuring that only deliberate, reproducible render-scene customizations
survive.

## Semantic Classification

Classification precedence is deterministic:

1. user exclusion or protected override;
2. Director actor or actor-set metadata;
3. saved layer convention;
4. block-instance and canonical geometry-signature evidence; and
5. conservative fallback to an ordinary mesh.

Every exportable object receives one role:

- `static_context`;
- `ordinary_actor`;
- `instance_candidate`;
- `batch_candidate`;
- `render_only`;
- `excluded`; or
- `unsupported`.

Layer paths provide semantic intent but never prove material or geometry
compatibility. Block names suggest reuse but never replace geometry hashing.
The compiler report records the winning rule and evidence for each nontrivial
classification.

## Coordinate And Unit Contract

The source snapshot records Rhino document units and its right-handed Z-up
basis. The Three.js scene GLB uses glTF's right-handed Y-up, meter-based
convention. Conversion is applied exactly once during package compilation.

The manifest keeps these values distinct:

- source origin;
- rebase origin; and
- applied render offset.

Actor pivots are transformed into package coordinates without changing their
local semantics. Large-coordinate scenes use an explicit recorded rebase
origin selected by the compiler profile. Coordinate conversion and rebasing
must pass fixed-camera pixel comparisons before publication.

## Balanced Optimization Profile

Balanced is a versioned profile family. The initial profile is `balanced@1`.
Profiles are immutable, and a scene link remains pinned until the user
deliberately adopts another version.

Immutability is enforced by a non-circular pair: an execution envelope is built
from completed runtime components first, and the profile descriptor then pins
that envelope. `execution-envelope.json` contains:

- envelope schema and component-manifest contract versions plus the Rook build
  and release identity;
- exact SHA-256 values for the RookNative binary and the managed companion
  assembly;
- explicit governed-file manifests for Python orchestration, bridge, capture
  contract, and `rook.threejs_scene` modules;
- the Python implementation, version, ABI, exact resolved dependency
  distributions, distribution-content hashes, and lockfile SHA-256;
- explicit governed-file manifests for the preview application, exact Three.js
  revision and bundle, `GLTFLoader`, shaders, and other runtime assets;
- Rhino SDK/OpenNURBS ABI, supported Rhino build range, operating-system and
  architecture requirements, supported WebView2 range, and required WebGL
  capabilities; and
- `executionEnvelopeSha256`, computed from canonical JSON with that field
  omitted.

Each governed-file manifest explicitly lists normalized component-relative
path, byte length, and file SHA-256 in ordinal path order. The versioned
`execution-envelope@1` schema fixes the governed roots and excludes only its
own generated file and generated `profile-descriptor.json` files. Runtime
verification enumerates those roots and rejects missing, changed, or unlisted
production files. Therefore inclusion rules do not live inside, or depend on,
the descriptor being hashed. The build order is component artifacts, component
manifests, execution envelope, then profile descriptor.

`profile-descriptor.json` contains:

- descriptor schema version, profile ID, and profile version;
- compiler contract version and `executionEnvelopeSha256`;
- enabled, report-only, and unsupported feature sets;
- material, geometry, coordinate, visual-equivalence, and capacity thresholds;
  and
- fixture, regression-test, and benchmark-evidence SHA-256 values.

`descriptorSha256` is computed from canonical JSON with that field omitted.
The descriptor and envelope are shipped together, copied unchanged into every
run, embedded by hash in the package manifest, and pinned in the scene link as
`{profileId, profileVersion, descriptorSha256,
executionEnvelopeSha256}`.

On Create, Update, recovery, and preview load, Rook verifies the descriptor and
envelope hashes, every governed component and dependency, and the active host
against the envelope constraints. The compilation report and journaled preview
evidence additionally record the exact Rhino, Windows, WebView2, WebGL
renderer, GPU, and driver versions used. The immutable guarantee is
deliberately narrow: it pins the optimization policy and exact
Rook/Python/Three.js implementation set, but does not claim byte-identical
output across all permitted Rhino, browser, or GPU builds. Per-run structural,
hash, and visible-equivalence validation remains required.

Reusing the same profile ID and version with a different policy or execution
envelope is `profile_descriptor_mismatch`; installed bytes, ABI, dependency,
or host constraints that do not match the pinned envelope are
`execution_envelope_mismatch`. Rook never silently re-pins either value. Any
behavior-affecting component or dependency change requires a new profile
version and explicit adoption.

Every Balanced version performs only transformations proven to preserve exact
geometry, material appearance, identity, pivots, transforms, and visible
output. `balanced@1` automatically applies compatible static-context merging
and material consolidation. It detects and reports instance and batch
candidates but keeps them as ordinary actor nodes until the Slice 2 evidence
gate authorizes a new Balanced version.

### Static context

- Bake source transforms into a common, rebased coordinate frame.
- Merge geometry by exact material and render-state signature.
- Emit one GLB primitive per compatible material bucket.
- Never merge geometry requiring independent visibility, selection, or motion.

### Repeated geometry

- In `balanced@1`, report eligibility and projected savings without changing
  the runtime representation.
- Detect identity with canonical local-space geometry hashes, including
  topology and all required vertex attributes.
- Treat block-definition identity as supporting evidence, not sole proof.
- Preserve one geometry payload and per-instance transforms.
- Map every actor ID to its package-specific instance entry.
- Fall back to ordinary nodes when geometry, material, pivot, or behavior is
  incompatible.

### Batchable actors

- In `balanced@1`, report eligibility and projected savings without changing
  the runtime representation.
- Group distinct geometries only when their normalized material, render state,
  vertex-attribute layout, and runtime behavior are compatible with
  `BatchedMesh`.
- Preserve independent matrices, visibility, selection, raycast identity, and
  actor addressing through the manifest.
- Keep unsupported or ambiguous actors as ordinary meshes.

### Material compatibility

The material signature includes normalized PBR factors, texture content hashes,
texture-coordinate sets and transforms, alpha mode and cutoff, sidedness,
vertex-color requirements, and normal/tangent requirements. Materials are
consolidated only when all appearance-affecting fields are equivalent. Names
alone do not affect compatibility; intentional property differences do.

### Explicit exclusions

Balanced does not automatically:

- decimate geometry;
- generate LODs;
- create texture atlases;
- alter UVs;
- approximate or replace materials;
- discard hidden source geometry permanently; or
- change pivots, actor identity, or animation semantics.

Objects that cannot be optimized safely remain visually complete ordinary
meshes and produce a warning, not a failed compilation.

## Evidence-Backed Profile Evolution

Every profile version records its fixtures, supported Three.js revision,
visual-equivalence thresholds, performance protocol, and benchmark evidence.
A new profile version requires regression tests and fresh browser measurements.
Evidence must distinguish correctness from performance; a faster result that
changes appearance or actor behavior is invalid.

The current stress harness is sufficient for Slice 1 ordinary meshes and
static-context merging. It must be extended before Balanced automatically
enables actor instancing or batching.

## Scene Package Contract

Each successful run contains:

```text
profile-descriptor.json
execution-envelope.json
scene.glb
scene.manifest.json
compilation-report.json
preview-prepared-evidence.json
preview-visible-evidence.json
```

Supported textures are embedded in the GLB for portable first-slice packages.
The GLB remains standards-compliant and visually complete in a normal glTF
viewer. The manifest adds Rook-specific synchronization, identity, and runtime
assembly data.

The manifest records:

- schema, package, profile, source snapshot, and render-scene versions plus the
  exact profile descriptor and execution-envelope SHA-256 values;
- candidate render-document filename, byte size, and SHA-256;
- GLB filename, byte size, and SHA-256;
- source units and basis plus package units, basis, and origins;
- canonical geometry and material signatures;
- deterministic merge, instance, and batch groups;
- actor IDs, actor-set IDs, pivots, and representation types;
- ordinary-node, instance, or batch lookup data;
- compilation warnings and unsupported features; and
- expected structural counts and validation evidence.

The compilation report records the finalized manifest SHA-256 and does not
refer to preview evidence, the scene link, or the current pointer.

Instance and batch indices are package-local implementation details. Consumers
always address actors by `actorId`; the runtime resolves the current index. A
new compilation may reorganize batches without breaking the actor API.

## Three.js Preview Runtime

The first production runtime pins the Three.js revision validated by the
stress harness. It does not import production behavior from the experiment;
shared logic is promoted into production-owned modules with dedicated tests.

The runtime:

1. reads `current.json` on startup to restore the last committed immutable run;
2. accepts `prepare(runId, expectedHashes)` only for an immutable candidate run
   named by the orchestrator;
3. verifies the profile descriptor, execution envelope, governed runtime
   components, GLB, and manifest hashes;
4. loads the GLB with `GLTFLoader` into a non-visible candidate scene;
5. builds and validates the ordinary actor index and manifest assembly plan;
6. removes replaced ordinary nodes only inside the candidate after successful
   runtime assembly;
7. verifies final actor addressability and expected structural counts and emits
   prepared evidence containing the finalized descriptor, envelope, render,
   GLB, manifest, and report hashes without changing the visible scene; and
8. accepts `commit(runId)` only for that prepared candidate, swaps it into view,
   and emits visible evidence. `discard` removes a prepared candidate,
   `restore` returns to a specified previously committed run, and
   `restoreEmpty` clears a partially committed first-Create preview.

It exposes a representation-neutral actor API for lookup, metadata inspection,
absolute-time transforms, visibility, selection, actor-set operations, and
translation of raycast results back to actor IDs.

Preview commit preserves the camera and timeline position when compatible. A
failed prepare leaves the previous scene visible. A failed commit participates
in the journaled rollback protocol and cannot finalize durable state. Preview
evidence includes the run ID, package, descriptor, and execution-envelope
hashes, actor-index hash, renderer-structure hash, actual renderer calls and
triangles, CPU measurements, GPU timing when available, exact host/runtime
versions, and package/profile provenance.

## User Experience

### Create Render Scene

First use requires the active authoring document to be saved and unmodified,
asks for or confirms the project root and a nonexistent, closed derived `.3dm`
path, selects the exact `balanced@1` descriptor and execution envelope by
default, creates the scene link, completes the first transaction, and opens the
Three.js preview.

### Update Render Scene

Subsequent source changes mark the scene stale. The explicit update command
requires the saved working derived document to be closed and shows these
stages:

```text
Capturing -> Synchronizing -> Preparing -> Compiling -> Validating -> Refreshing
```

The successful summary reports:

- added, changed, deleted, and unchanged source objects;
- layer and material preparation actions;
- ordinary, merged, instanced, and batched counts;
- before/after nodes, meshes, materials, draw calls, triangles, and bytes;
- actor-addressability and visible-equivalence results;
- profile, execution-envelope, and package versions; and
- unoptimized objects and reasons.

The preview exposes current, stale, running, cancelled, and failed states plus
links to the derived `.3dm`, current package, and report. While a promotion
journal exists, the only state is recovering; no run is presented as current
until recovery completes.

### Relink and render customization

**Relink Render Scene** is the only Slice 1 operation that changes the source
path binding after Save As, move, or rename. **Set Render Material Override**
and **Clear Render Material Override** are the only operations that stage
material override intent. **Adopt Render-Only Object** and **Remove Render-Only
Object** stage registration intent for render-only geometry and helpers. These
actions update the working document's draft registry and markers, mark the
scene stale, and never mutate the committed scene link. The user saves and
closes the working document, then Update either publishes the draft with the
whole scene or preserves it for retry.

### Preserved conflicts

When recovery retains unexpected user bytes, the UI reports the retained path,
size, SHA-256, source operation, and reason. It offers **Review Preserved
Conflict**, **Acknowledge And Keep Conflict**, and the separately confirmed
**Delete Preserved Conflict** action. No age, quota, successful update, or
acknowledgement alone deletes retained bytes.

## Failure And Recovery

Failures are stage-specific and include an object ID, actor ID, layer, material,
or package entry when available. Blocking conditions include duplicate actor
IDs, invalid geometry, unsafe paths, unavailable required textures, unsaved
render-scene edits, an open or locked derived document, invalid customization
drafts, execution-envelope mismatch, invalid GLB output, actor-mapping mismatch,
visible divergence, browser assembly failure, or WebGL context loss.

Warnings are non-blocking when the compiler can preserve the original ordinary
representation exactly. Unsupported optimization never justifies dropping an
object.

An ordinary failed or cancelled run does not advance `current.json` or the
scene link. Cleanup is manifest-driven and limited to attempt-owned staging
files; retained conflict records and bytes are never cleanup candidates.
Published run directories are immutable. The previous committed render
snapshot, package, report, and preview remain the last known-good publication.
The user-facing working derived document may remain deliberately stale with a
saved customization draft and is reported separately from that publication.

An operating-system or process interruption after `promotion.json` is durable
is not classified as an ordinary failed run. On startup, Rook reports
`recovering`, blocks normal current-state presentation, and follows the
journaled completion-or-rollback rules before accepting another command. A
recovery may legitimately make the candidate current only after it
re-establishes matching render-document, pointer, profile, envelope, package,
actor, and visible-preview evidence. Otherwise it restores the nullable prior
state, including an empty first-Create state. Recovery itself is tested as a
distinct outcome from ordinary failure.

## Staged Delivery

### Slice 1: End-to-end render-scene workflow

- Create and persist the scene link and derived render `.3dm`.
- Detect source additions, changes, and deletions.
- Apply layer and material semantic classification.
- Preserve ordinary actor nodes, metadata, pivots, and absolute-time behavior.
- Merge exact-compatible static context by material.
- Produce and validate GLB, manifest, report, and automatic preview refresh.
- Preserve render-only cameras, lights, environments, and registered material
  overrides.
- Publish transactionally and retain the last known-good result.
- Report instance and batch candidates without applying them.

### Slice 2: Instancing and batching

First extend the benchmark harness to compare ordinary meshes,
`InstancedMesh`, and `BatchedMesh` across actor counts, geometry diversity,
materials, transforms, visibility, selection, raycasting, and deterministic
animation. After the evidence gate passes, implement manifest-driven runtime
assembly and enable those Balanced decisions.

### Slice 3: Profile refinement and scale

Add evidence-backed profile revisions, incremental compiled-result reuse,
richer material support, representative large Rhino fixtures, capacity
policies, and improved override management.

## Testing

### Pure tests

- canonical geometry and material signatures;
- scene diffing and dependency invalidation;
- semantic classification precedence;
- Balanced decisions and conservative fallbacks;
- scene-link and manifest schema validation;
- source-path canonicalization, version fingerprints, Save As rejection, and
  explicit relinking;
- profile descriptor and execution-envelope canonicalization, non-circular
  governed-file coverage, hash enforcement, ABI/dependency rejection, and
  host-constraint validation;
- actor mapping across representation changes;
- customization-draft operation, tombstone, base-run, marker, and retry
  behavior;
- material-override marker, precedence, clearing, and tamper behavior;
- nullable-prior journal schemas and hash-safe presence/absence rollback;
- acyclic publication-DAG ordering, phase-available hashes, and explicit
  self-hash-field omission;
- canonical candidate base-state tokens and byte-for-byte comparison;
- destination-lock identity independent of `sceneId`, canonical lock ordering,
  and scene-lock composition;
- retained-conflict record validation, cleanup exclusion, acknowledgement, and
  hash-checked explicit deletion;
- safe path normalization and attempt-owned cleanup; and
- deterministic reports and hashes.

### Rhino integration tests

- source capture for meshes, Breps, blocks, layers, materials, pivots, and
  Director metadata;
- initial derived-document creation;
- rejection of an open-but-saved derived document before any candidate or
  journal write, followed by success after it is saved and closed;
- injection of an old derived-document open after the last pre-check but before
  replacement, proving post-replacement detection, no preview/pointer commit,
  conflict preservation, and journaled rollback both when it remains open and
  when it saves and closes before post-replacement enumeration;
- add, change, delete, hierarchy, layer, and material synchronization;
- preservation of render-only cameras, lights, environments, and overrides;
- staging customization intent without changing the committed scene link,
  publishing it only through Update, and preserving the saved draft on failure;
- detection of unsaved or unclassifiable render-scene changes;
- preservation and rejection rules for every supported render-document edit;
  and
- proof that the authoring document remains unchanged.

### Package and browser tests

- GLB framing, bounds, attributes, materials, embedded textures, and SHA-256;
- `GLTFLoader` round trips and exact metadata survival;
- actor lookup, pivots, transforms, visibility, selection, and raycasts;
- ordinary-versus-optimized fixed-camera pixel equivalence;
- unit, basis, and large-coordinate comparisons;
- actual renderer calls and triangle counts;
- CPU/GPU protocol results across declared presets; and
- stop, reset, cancellation, context loss, preview prepare/commit/restore, and
  last-known-good refresh behavior.

### Process-boundary and recovery tests

- MCP-unavailable, native-unavailable, companion-unavailable, WebView2-failed,
  and WebGL-failed capability outcomes;
- main-thread enforcement for every Rhino SDK access;
- stale run-ID rejection across native and managed callbacks;
- cancellation between each bounded native, compiler, and writer phase;
- mutation of each current, scene-link, source, working-document, draft,
  descriptor, and envelope base token after candidate preparation but before
  journaling, each producing `candidate_base_stale` with no journal or
  publication write;
- two candidates built from one base, proving only the first can publish;
- two concurrent first Creates with different provisional scene IDs and the
  same canonical destination, proving they contend on one destination lock and
  only one can journal or publish;
- two concurrent recovery workers for one journal, proving both acquire the
  destination-then-scene lock order, exactly one mutates state, and the other
  returns `already_recovered` after its locked reread;
- recovery after mutex abandonment by a crashed owner, proving no journaled
  mutation occurs before the new owner reacquires both locks and rereads;
- promotion interruption after every journal phase for both Update and first
  Create;
- first-Create rollback to absent derived document, absent pointers, and empty
  preview, with deletion allowed only for journal-matching candidate hashes;
- Update rollback that restores a saved stale customization draft exactly;
- mutation of every governed native, managed, Python, dependency, and preview
  component plus Python ABI and host-constraint mismatch; and
- proof that recovery either completes one fully evidenced candidate or
  restores one fully evidenced nullable prior state, never a mixed accepted
  state.

## Slice 1 Acceptance Criteria

A representative checked-in Rhino fixture contains static context, multiple
materials, repeated blocks, ordinary actors, Director metadata, and render-only
presentation content. Acceptance requires:

- Create Render Scene produces the derived `.3dm`, GLB, manifest, report, and
  live browser preview without changing the source file, and refuses an
  existing derived destination on first Create.
- Create and Update reject untitled or modified source documents, bind to the
  canonical saved path under the explicit project root, treat case-only path
  changes as equivalent, and require Relink after Save As or a real move.
- A second update adds, modifies, and deletes source objects and the changes
  appear across the derived scene and browser preview.
- Update rejects the saved derived document while it is open, performs no
  candidate construction or durable writes, and succeeds after the document is
  closed.
- An injected open in the final check/replacement window is detected from the
  Rhino document's in-memory run marker after replacement and forces journaled
  rollback before preview or pointer commit.
- Actor IDs, actor sets, pivots, materials, and transforms survive both runs.
- Render-only cameras, lights, environment, and registered overrides survive
  the second update.
- A staged material override does not change the committed scene link, survives
  a failed Update as a stale working draft, enters the link only on successful
  Update, survives a changed source material, and returns to source inheritance
  after a successfully published clear tombstone. Manual unregistered material
  changes are overwritten with a warning.
- The scene link, manifest, copied descriptor, copied execution envelope,
  active native/managed/Python/preview components, dependencies, and preview
  agree on the exact descriptor and envelope hashes. A same-name/version policy
  mutation or any governed component, dependency, or ABI mismatch blocks Update
  and promotion.
- The publication hash graph follows the declared order, no artifact hashes
  itself or a future output, and the initial journal marks visible evidence,
  scene link, and current pointer pending until each is finalized.
- Changing any candidate base-state token during compilation, or racing two
  candidates from the same base, prevents the stale candidate from creating a
  promotion journal or replacing the working document.
- Concurrent first Creates with different provisional `sceneId` values but the
  same canonical destination serialize on one path lock; one publishes and the
  other exits stale without creating a journal.
- Concurrent recovery workers reacquire destination then scene locks and reread
  the journal under lock, so exactly one changes journaled state.
- Conflict-preservation bytes and their path/hash record survive ordinary
  cleanup, successful recovery, and acknowledgement; only the explicitly
  confirmed, hash-checked delete action removes them and leaves a tombstone.
- Static-context merging reduces actual browser draw calls while passing the
  fixed-camera visible-equivalence gate.
- Instance and batch candidates are reported deterministically but remain
  ordinary actor nodes in Slice 1.
- Ordinary failure injected before and during every live transaction phase
  preserves the first run as the current publication and preview and preserves
  any saved stale working draft for retry.
- First-Create interruption injected after every durable journal phase either
  completes the fully evidenced first run or restores absent derived/pointer
  state and an empty preview without deleting unexpected bytes.
- Interruption injected after every durable promotion-journal phase recovers by
  either completing the fully evidenced second run or restoring the fully
  evidenced first run; both outcomes clear the journal and leave no mixed
  current state.
- The public Slice 1 Create and Update tools require MCP Python, discovered
  RookNative, managed WebView2, and WebGL; each missing capability returns its
  declared blocking reason without advancing current state.
- The source worktree and production dependency boundaries remain clean and
  explicit.

## Out Of Scope

- automatic background synchronization;
- bidirectional geometry merging;
- geometry decimation or remeshing;
- texture atlasing;
- automatic LOD generation;
- cloud hosting or public deployment;
- non-Rhino authoring sources;
- silently upgrading a scene link to a newer optimization profile; and
- using the experiment directory as a production runtime dependency.

## Follow-On Decision

After Slice 1 acceptance, extend the stress harness for instancing and batching.
Only measured, correctness-preserving results may define a new Balanced version
and authorize Slice 2 runtime representations.
