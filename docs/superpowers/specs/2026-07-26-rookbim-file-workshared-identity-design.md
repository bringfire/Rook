# RookBIM File-Workshared Document Identity Design

**Date:** 2026-07-26

**Status:** Decision-gated draft specification awaiting review and CreationGUID probe

**Target:** `src/Rook` BIM contracts and `src/RookBim` Revit identity implementation

**Deployment unit:** Separate RookBIM identity release after the decision gate passes

## Purpose

Replace RookBIM's server-only central-GUID assumption and fail-open document matching with one evidence-backed, host-specific document identity resolver.

The target invariant is:

> RookBIM resolves, selects, or exports an element identity only after trustworthy document evidence proves that the identity belongs to the active Revit document. Missing, conflicting, detached, unsupported, or incomparable evidence fails closed before `UniqueId` or `ElementId` lookup.

This is a decision-gated design. A live Revit 2024 `Document.CreationGUID` probe must determine whether the preferred file-based composite key is suitable. Implementation planning cannot proceed past the probe gate until its report is reviewed and the selected key strategy is recorded in this specification.

Path-only identity is never approved for durable resolution. A path identifies a location, not a model; replacing a model at the same path would create an unsafe false positive.

## Linked incident

This design and [Rhino.Inside.Revit Grasshopper Document Lifecycle Design](2026-07-26-rir-grasshopper-document-lifecycle-design.md) came from the same Revit 2024.3 investigation but correct independent runtime boundaries.

Gated RookBIM diagnostics proved that a file-workshared model reached category item 380 and serialized successfully, but `Document.WorksharingCentralGUID` threw `Autodesk.Revit.Exceptions.InternalException`. The first fix stopped the route failure by returning no persistent document GUID for file-based worksharing. That exposed a preexisting safety defect: `DocumentMatches` treats an incoming identity without a persistent GUID as matching every active document.

The later Grasshopper/RiR incident concerns `GH_DocumentServer` registration and solver ownership. It has a separate specification, implementation plan, release, live report, and rollback path.

## Installed API evidence

The installed Revit 2024 API documents distinct properties with distinct applicability:

- `Document.CreationGUID`: a unique identifier generated when the document was first created; introduced in Revit 2024.
- `Document.WorksharingCentralGUID`: the central GUID of a Revit Server model; it throws `InapplicableDataException` when the central model is not a qualifying server-based model.
- `Document.WorksharingProjectGUID`: the project GUID for a cloud-based central model.
- `Document.CloudModelGUID`: the GUID of a cloud model.
- `Document.GetWorksharingCentralModelPath()`: the central model path for a workshared document and invalid for a non-workshared document.
- `Document.IsDetached`: identifies a detached workshared document; detached documents may have empty title and path.

The current `SupportsWorksharingCentralGuid` implementation incorrectly treats a cloud model as supporting `WorksharingCentralGUID`. The new resolver removes that branch. Server, cloud, file-workshared, saved non-workshared, family, unsaved, and detached documents follow explicit typed paths.

## Goals

This design will:

- probe `CreationGUID` before selecting the file-based durable key;
- introduce versioned `documentKey` and `documentKeySource` fields;
- keep GUID-named fields restricted to actual GUID values;
- define identity behavior for every supported Revit document class;
- use distinct typed key sources for Revit Server, cloud, and file/path-based documents;
- centralize Revit document classification, evidence acquisition, normalization, key derivation, diagnostics, and comparison;
- acquire immutable document evidence once per operation and reuse it for every identity;
- degrade expected identity-property failures to unavailable evidence without failing producer routes;
- define byte-exact Windows path and key encoding;
- remove the incorrect cloud-to-`WorksharingCentralGUID` branch;
- replace boolean/fail-open matching with a closed comparison result;
- prevent a strong-key mismatch or verification failure from downgrading to legacy evidence;
- reject conflicting strong and legacy evidence;
- fail closed before element lookup when evidence is unavailable;
- preserve raw path fields temporarily for wire compatibility while excluding them from authorization;
- explicitly supersede the Phase 1 doctrine and tests that prohibit executable fallback identity;
- delete scattered or obsolete identity branches once the authoritative resolver replaces them;
- validate resolution, selection, and export against two simultaneously open documents.

## Non-goals

This design will not:

- treat a path hash alone as durable model identity;
- treat a process-local title, filename, or active-document position as identity;
- authorize resolution using raw `Path`, `DocumentPath`, `Title`, or `DocumentTitle`;
- use category, view, element, or model names as identity material;
- alter the separate RookBIM diagnostic sink architecture;
- change linked-document support beyond applying the same active-document gate before current linked-evidence handling;
- add Revit references to `src/Rook`;
- remove raw path fields from the existing wire contract without a separately versioned breaking-contract design;
- support Revit releases before 2024 in the first composite-key implementation;
- generalize the resolver into a repository-wide identity framework.

## Decision gate: CreationGUID probe

### Purpose

The installed documentation describes `CreationGUID`, but it does not establish how central creation, local creation, Save As Central, copied files, detach, and reopen affect the value. The production design therefore depends on a live matrix rather than API-name inference.

### Required cases

The probe uses disposable test models and records only bounded alias/equality evidence. It must cover:

1. A newly created saved non-workshared project.
2. The same project after close and reopen.
3. A file-workshared central model.
4. A standard local created from that central model.
5. The same local after close and reopen.
6. A copied central or Save As Central at a different path.
7. A detached copy of the workshared model.
8. A saved family document.
9. An unsaved project and unsaved family document.
10. Using disposable files, a different newly created document placed at a previously used path.

For each case, record:

- document class from the matrix below;
- whether each property read succeeded;
- whether `CreationGUID` is non-empty;
- equality relationships to the central, local, copy, reopen, and replacement cases;
- `IsWorkshared`, `IsDetached`, `IsModelInCloud`, central/local classification, and ModelPath kind;
- per-report opaque equality aliases for canonical path and GUID evidence, never raw values or deterministic path hashes in the report;
- Revit version, Rook/RookBIM commit, process ID, and UTC timestamps.

The probe must read each Revit property independently so one exception cannot hide later evidence. It runs in a valid Revit API context. Diagnostic-only reads catch locally and do not alter route behavior.

The probe maintains an in-memory alias table scoped to one report. The first distinct canonical path becomes `path-001`, the first distinct creation GUID becomes `creation-001`, and so on; equal values within that report reuse the same alias. Only aliases and explicit same/different relationships are persisted. The alias-to-value table is destroyed when the report closes and is never written. Aliases are not compared across reports, and the report contains no deterministic unsalted hash from which a guessed path or GUID can be confirmed.

### Composite-key suitability criteria

The preferred `CreationGUID + canonical path` key is suitable for a document class only if:

- `CreationGUID` is readable, non-empty, and stable on repeated reads;
- it remains equal between a file central and its standard local;
- it remains stable after closing and reopening the same saved document;
- the required path is absolute, convertible, and stable for the intended central/local relationship;
- a copied central is distinguished by at least one composite input;
- a different document replacing the same path is distinguished by `CreationGUID`;
- no observed exception or transition makes identical live documents alternate between key sources.

Detached documents are rejected regardless of their observed values. Their probe results are descriptive, not authorization evidence.

### Decision outcomes

The reviewed probe report selects one of these outcomes:

1. **Composite approved:** implement the preferred composite key for every document class whose criteria pass.
2. **Class-limited composite:** implement it only for passing classes and explicitly fail closed for the others.
3. **Composite rejected:** do not implement path-only durable matching; retain only report-local diagnostic aliases/equality results and fail closed for affected classes while a new design is reviewed.

Path-only authorization is not an outcome. A future process-scoped random document-instance key could safely authorize only the exact open `Document`, but that additional state owner is not part of this design and requires separate approval if needed.

Implementation planning may describe the probe task and the code paths conditional on its result, but production implementation does not begin until the result is written into this specification and approved.

## Wire contract

### New fields

`BimDocumentIdentity` gains:

- `DocumentKey` (`documentKey`): a versioned opaque string or `null`;
- `DocumentKeySource` (`documentKeySource`): a closed typed source.

`BimElementIdentity` gains:

- `DocumentKey` (`documentKey`): copied from the owning document identity;
- `DocumentKeySource` (`documentKeySource`): copied from the owning document identity.

Candidate key-source values are:

- `revit_server_central_guid_v1`;
- `revit_cloud_project_model_v1`;
- `revit_creation_guid_central_path_v1`;
- `revit_creation_guid_document_path_v1`;
- `unavailable`.

Only sources approved by the probe matrix are emitted. The version is part of the source and key prefix so normalization or evidence changes cannot silently compare under the old contract.

### Key representation

Keys are opaque identifiers, not GUID fields. Each uses a source-specific prefix and lowercase SHA-256 of an unambiguous canonical payload.

Examples:

```text
revit-server-v1:<64 lowercase hex>
revit-cloud-v1:<64 lowercase hex>
file-document-v1:<64 lowercase hex>
saved-document-v1:<64 lowercase hex>
```

Payloads use a fixed ASCII domain/version label, NUL separators, lowercase `D`-format GUID text, and the normalized path where required. Length, prefix, character set, and source/prefix pairing are validated before comparison.

### Legacy GUID fields

`Guid` and `DocumentGuid` continue to contain only actual Revit GUID values or `null`. A path hash or composite hash is never stored in either field.

`BimDocumentGuidSource.PathFallback` remains temporarily for wire compatibility but is deprecated and is not emitted by the new resolver. The resolver treats an incoming legacy `path_fallback` GUID source as incomparable, because no GUID-named value can correctly represent that evidence.

For a Revit Server document, the legacy GUID may continue to be the actual `WorksharingCentralGUID`. Cloud and other document classes do not call `WorksharingCentralGUID`. The new resolver emits no legacy `Guid`/`DocumentGuid` projection for cloud documents; their authoritative identity is the typed cloud document key. Existing cloud payloads that contain a legacy GUID are accepted only under the no-strong-key legacy rules and therefore fail closed as incomparable.

`CreationGUID` is key material only. It is never projected into legacy `Guid` or `DocumentGuid` for file-workshared, saved-project, or saved-family sources. Those legacy fields are `null` unless the selected source has an explicitly approved legacy projection; in this design, only Revit Server's actual `WorksharingCentralGUID` has one.

### Raw paths

Existing `Path` and `DocumentPath` fields remain in the current wire version for compatibility. This is intentional retention, not an identity fallback.

They:

- remain display/provenance data;
- may contain sensitive filesystem information;
- are not persisted in diagnostic JSONL;
- are never compared to authorize resolution;
- are never hashed ad hoc by consumers to reconstruct a key;
- may be removed or redacted only in a separately versioned contract.

The new key hides its path material, but this does not claim the entire existing response is path-private.

## Authoritative resolver

One `RevitDocumentIdentityResolver` under `src/RookBim/Revit` owns all Revit-specific identity evidence. Callers no longer decide which property applies.

The resolver owns:

- document-class classification;
- `IsDetached`, `IsWorkshared`, `IsModelInCloud`, central/local, project/family, and saved/unsaved reads;
- `CreationGUID` reads;
- Revit Server `WorksharingCentralGUID` reads;
- cloud `WorksharingProjectGUID` and `CloudModelGUID` reads;
- worksharing central `ModelPath` acquisition;
- user-visible path conversion and normalization;
- key derivation and validation;
- legacy GUID projection;
- document identity DTO construction;
- comparison and closed failure results;
- diagnostic stages for every production read.

No caller directly reads these GUID/path properties for identity. The current `GetWorksharingCentralGUID`, `SupportsWorksharingCentralGuid`, and boolean `DocumentMatches` branches are deleted after replacement coverage exists.

### Operation-scoped evidence ownership

Each Revit work item resolves one immutable `RevitDocumentIdentityEvidence` snapshot inside the valid Revit API context before producing or consuming identities. The snapshot contains the owning `Document` reference as a non-serialized scope token, document classification, selected key/source or unavailable reason, approved legacy projection, and already-read DTO display fields. It contains no lazy Revit getters, delegates, raw exceptions, or cross-request mutable state.

The operation passes that snapshot explicitly to document and element identity projection. Every element identity in a query/list/export response reuses the same snapshot; projection never calls back into document classification, GUID, ModelPath, normalization, or hashing. Element projection verifies by reference that `element.Document` is the snapshot's owner before copying document evidence.

Identity-consuming operations likewise resolve the active-document snapshot once, compare every incoming identity against that same snapshot, and complete all document-identity validation before any selection, mutation, export, `UniqueId`, or `ElementId` lookup. A batch never recomputes active-document evidence per identity and never partially acts on identities before a later document-evidence failure.

The snapshot lifetime is exactly one operation. It is not stored in static state, `AsyncLocal`, a global dictionary, a `Document`-keyed cache, or a handler field, and it is not reused by a later request. Cross-request or document-lifecycle caching requires a separate invalidation design and is outside this specification.

### Identity-read failure containment

The resolver reads each classification, GUID, ModelPath, conversion, and normalization stage independently. A closed availability wrapper converts expected data/applicability failures into unavailable evidence. Its Revit exception allowlist includes `InapplicableDataException`, `InvalidOperationException`, `InternalException`, `InvalidObjectException`, and the Revit argument/null exceptions documented by an invoked conversion API. Path/key construction also treats `System.ArgumentException`, `NotSupportedException`, `PathTooLongException`, `System.Security.SecurityException`, `System.Text.EncoderFallbackException`, and `System.Security.Cryptography.CryptographicException` as unavailable evidence. The resolver does not catch `Exception` indiscriminately; programming defects and process-fatal exceptions remain subject to the operation-level error boundary.

If a required identity input fails with an expected exception, the snapshot records a bounded unavailable reason, emits `DocumentKey = null`/`DocumentKeySource = unavailable`, and retains no exception object. Other independent DTO evidence may still be read. Diagnostics observe the exact failed stage and bounded exception facts but do not change the returned snapshot.

Identity-producing routes—including `active_document`, `list_categories`, and query/list responses—continue their otherwise successful work and return HTTP 200 with `documentKey: null` when trustworthy identity evidence is unavailable. Element identities produced by that operation also carry a null document key. Identity-consuming routes fail closed with `document_identity_unavailable` before element lookup or side effects. Thus failure of `CreationGUID`, ModelPath, a host-specific GUID, conversion, normalization, or hashing cannot recreate the original route-wide `list_categories` failure.

## Document-class matrix

| Document class | Required evidence | Preferred authoritative key | Unsupported/failure behavior |
|---|---|---|---|
| File-workshared central | Not detached; suitable `CreationGUID`; absolute normalized file central `ModelPath` | `revit_creation_guid_central_path_v1` | `document_identity_unavailable` |
| File-workshared local | Not detached; same suitable `CreationGUID` as central; same normalized central `ModelPath` | Same composite as its central | `document_identity_unavailable` |
| Revit Server central/local | Not detached; server `ModelPath`; non-empty `WorksharingCentralGUID` | `revit_server_central_guid_v1` | `document_identity_unavailable`; never fall back to cloud/file reads |
| Cloud workshared | Not detached; cloud classification; non-empty `WorksharingProjectGUID` and `CloudModelGUID` | `revit_cloud_project_model_v1` | `document_identity_unavailable`; never call `WorksharingCentralGUID` |
| Saved non-workshared project | Suitable `CreationGUID`; absolute normalized `PathName` | `revit_creation_guid_document_path_v1` if its probe criteria pass | Explicit fail closed if the class is not probe-approved |
| Saved family document | Suitable `CreationGUID`; absolute normalized `PathName`; family classification included in domain payload | `revit_creation_guid_document_path_v1` if its probe criteria pass | Explicit fail closed if the class is not probe-approved |
| Unsaved project | No durable path | `unavailable` | Identity may be returned for display, but resolution/selection/export by identity fails closed |
| Unsaved family | No durable path | `unavailable` | Same fail-closed behavior |
| Detached document | Rejected before key derivation | `unavailable` | `document_identity_unavailable`; never use retained central/path/GUID values |

Linked RVT documents do not bypass this matrix. The active host document must match first; current linked-evidence policy then applies separately.

The matrix makes functional changes explicit: identity-based operations on unsaved and detached documents are unsupported in this design, and any saved class rejected by the CreationGUID probe also fails closed.

## Canonicalization and key derivation

### File central path

For file-workshared central/local documents, the resolver obtains `GetWorksharingCentralModelPath()` only after workshared, non-detached, non-cloud, non-server classification. It rejects null, server, cloud, or unconvertible ModelPaths. A qualifying file ModelPath is converted exactly once with `ModelPathUtils.ConvertModelPathToUserVisiblePath(modelPath)` and then passed to the shared Windows canonicalizer below.

The Windows canonicalizer is byte-contract code and executes this exact sequence for both converted central paths and saved `Document.PathName` values:

1. Reject null, empty, whitespace-only, or embedded-NUL input. Do not trim the input.
2. Replace every `/` (U+002F) with `\` (U+005C).
3. Reject device/NT namespace prefixes `\\?\`, `\\.\`, and `\??\` using ordinal-ignore-case comparison.
4. Accept only a drive-absolute form beginning with `[A-Za-z]:\`, or a UNC form beginning with `\\` and containing non-empty server and share segments. Reject relative, root-relative, drive-relative, URI, and incomplete UNC forms before calling `Path.GetFullPath`.
5. Call `System.IO.Path.GetFullPath` exactly once to collapse `.`/`..` segments and redundant separators. Replace any `/` in its result with `\` and repeat the device/absolute-form validation.
6. Obtain `Path.GetPathRoot`. Reject a null/empty root. If the full path is longer than the root, remove all trailing `\`; otherwise preserve the drive root (`C:\`) or UNC share root (`\\SERVER\SHARE\`) including its final separator.
7. Apply `ToUpperInvariant()` to the entire resulting string. Apply no Unicode normalization and perform no trimming.

The canonical output therefore always uses `\`, has an uppercase invariant representation, and preserves an absolute Windows root. The resolver performs no filesystem existence lookup, symlink/junction resolution, 8.3-name expansion, network access, or mapped-drive-to-UNC conversion.

Mapped-drive and UNC representations can therefore produce a safe false negative. They can never authorize a different model because the key also requires the probe-approved `CreationGUID`.

### Saved non-workshared and family path

These classes use absolute normalized `Document.PathName`, not `GetWorksharingCentralModelPath`. Their payload includes a class-domain token so a project and family cannot compare under an accidentally shared input set.

### Source-specific payloads

Conceptual payloads are:

```text
rookbim:revit-server:v1\0<worksharing-central-guid>
rookbim:revit-cloud:v1\0<worksharing-project-guid>\0<cloud-model-guid>
rookbim:file-workshared:v1\0<creation-guid>\0<normalized-central-path>
rookbim:saved-project:v1\0<creation-guid>\0<normalized-document-path>
rookbim:saved-family:v1\0<creation-guid>\0<normalized-document-path>
```

GUID payload values use lowercase `D` format. Each `\0` above is one NUL byte (`0x00`) between fields. The complete payload string is encoded with strict UTF-8 without a BOM; invalid UTF-16 input is rejected rather than replacement-encoded. SHA-256 runs over those exact bytes, and the final wire key is the source prefix plus exactly 64 lowercase ASCII hexadecimal characters. Raw payloads are not persisted in diagnostics.

## Matching and downgrade prevention

The resolver replaces `DocumentMatches` with a closed result such as:

- `Match`;
- `Mismatch`;
- `Unavailable`;
- `InvalidEvidence`.

The comparison order is normative.

### Incoming versioned key present

1. Validate key syntax, source, version, and source/prefix agreement.
2. Resolve the active document using that exact supported source/version.
3. If the active document cannot produce comparable evidence, return `Unavailable`.
4. If values differ, return `Mismatch`.
5. If values match, validate any supplied legacy strong GUID evidence for consistency. Revit Server may compare its actual central GUID; for sources with no approved legacy GUID projection, any non-null legacy GUID is conflicting evidence.
6. If supplied strong evidence conflicts or cannot be validly projected for that source, return `InvalidEvidence`.
7. Only a fully consistent result is `Match`.

A mismatching, malformed, unknown-version, unsupported, or unverifiable versioned key never falls back to a legacy GUID, raw path, title, `UniqueId`, or `ElementId`.

### No incoming versioned key

Legacy comparison is allowed only when no stronger key was supplied.

- A qualifying legacy Revit Server identity with an actual persistent GUID may compare to the active server document's actual central GUID.
- Legacy cloud/file/path-fallback/unavailable identities without an approved comparable key fail closed.
- Raw `DocumentPath` and `DocumentTitle` never authorize a match.
- Absence of document evidence returns `Unavailable`, never `true`.

### Error mapping

- `Mismatch` → existing `document_mismatch`, HTTP 409.
- `Unavailable` → new `document_identity_unavailable`, HTTP 409. The request is syntactically valid but conflicts with the active document's inability to establish trustworthy comparable identity.
- `InvalidEvidence` → new `document_identity_invalid`, HTTP 400. Malformed, unknown-version, source/prefix-inconsistent, or conflicting incoming evidence is a bad request.

These failures occur before `document.GetElement(identity.UniqueId)` or ElementId fallback. No element lookup may turn unavailable document evidence into an implicit match.

## Diagnostics and privacy

Production identity reads use the existing diagnostic production-probe contract and preserve disabled fast paths. Add closed stages for:

- document classification;
- `CreationGUID`;
- server central GUID;
- cloud project GUID;
- cloud model GUID;
- central ModelPath;
- path conversion/normalization result;
- key-source selection;
- comparison outcome.

Diagnostics record stage, outcome, detail code, exception type, and HResult under existing bounds. They never persist:

- GUID values;
- document keys;
- raw or normalized paths;
- titles or filenames;
- request identities.

Expected identity-read exceptions follow the failure-containment contract above whether diagnostics are enabled or disabled: producing routes continue with unavailable evidence, and consuming routes fail closed. Optional diagnostic-only probes catch locally and never affect the snapshot. The diagnostic flag must not select a different key, matching result, HTTP status, or route-success outcome.

## Cleanup and doctrine

The implementation replaces rather than layers over obsolete behavior. It removes or supersedes:

- the cloud branch in `SupportsWorksharingCentralGuid`;
- universal use of `WorksharingCentralGUID` as document identity;
- scattered direct document-identity property reads;
- boolean `DocumentMatches`;
- the unconditional `true` result for missing persistent GUID evidence;
- tests requiring `PathFallback` to remain absent from executable identity design;
- tests that treat unavailable document evidence as a universal match;
- Phase 1 language declaring `path_fallback` only diagnostic/non-stable without describing the new versioned key contract.

The Phase 1 design receives a superseded notice linking here. Historical context remains readable, but its old rule no longer governs the new `documentKey` contract.

Compatibility fields retained intentionally are not behavior owners. No new compatibility resolver runs in parallel with `RevitDocumentIdentityResolver`.

Cleanup is limited to document identity production and comparison. It does not authorize unrelated export, selection, category, link, or diagnostic refactoring.

## Commit and deployment boundaries

This specification has its own implementation plan and release, independent of the Grasshopper lifecycle design.

Expected reviewable boundaries are:

1. Operator-assisted CreationGUID probe and durable redacted report; update this specification with the approved decision.
2. Pure key contract/derivation and comparison tests, kept behavior-neutral and unused by production routes.
3. One production resolver cutover that adds contract fields, centralizes all document classes, removes fail-open matching and incorrect GUID branches, replaces obsolete tests, and updates doctrine.

No production identity implementation or deployment occurs before step 1 is reviewed. Any preparatory code must remain unused and behavior-neutral until the resolver cutover.

`src/RookBim/RookBim.csproj` remains Revit-specific and must build after `src/Rook/Rook.csproj`. Core contracts and optional module stay version-aligned. The deployed `/bim/status` commit must identify the exact code under acceptance.

## Testing

### Probe report tests

The probe harness/report must prove:

- every required document class was attempted or explicitly marked unavailable with reason;
- properties were read independently;
- no raw model title, filename, path, or GUID appears in the durable report;
- equality relationships are recorded through report-local opaque aliases and explicit booleans;
- no deterministic path or GUID hash is persisted;
- exact Revit and build provenance is present;
- detached values are never promoted to identity evidence.

### Contract and resolver tests

Tests must cover:

- all document-key source values and wire names;
- GUID fields reject/non-emit hashes;
- `CreationGUID` is never projected into legacy `Guid`/`DocumentGuid` for file or saved-document sources;
- key prefix/source/version validation;
- golden byte/hash vectors for every source payload;
- byte-exact Windows case and separator normalization for drive and UNC paths;
- drive-root and UNC-share-root preservation plus non-root trailing-separator removal;
- rejection of empty, relative, drive-relative, root-relative, URI, incomplete UNC, embedded-NUL, and device-namespace paths;
- strict UTF-8 without BOM and lowercase 64-character SHA-256 output;
- mapped/UNC differences produce non-match, not normalization guesses;
- server code calls only server GUID APIs;
- cloud code calls only cloud GUID APIs and never `WorksharingCentralGUID`;
- file central/local code uses the approved composite only;
- saved project and family behavior follows the probe decision;
- unsaved and detached behavior fails closed;
- every matrix row has a test;
- strong key match/mismatch/unavailable behavior;
- unknown key version fails without downgrade;
- malformed key fails without downgrade;
- conflicting key and legacy GUID is invalid;
- legacy GUID comparison runs only when no document key is supplied;
- raw path/title never participates in authorization;
- element `UniqueId` and `ElementId` lookups occur only after `Match`;
- expected Revit identity exceptions, including `InternalException`, produce unavailable snapshots rather than route-wide producer failures;
- `active_document`, `list_categories`, and query/list producers remain HTTP 200 with null document keys when evidence is unavailable;
- consumers return HTTP 409 `document_identity_unavailable` or HTTP 400 `document_identity_invalid` as specified, before lookup or side effects;
- for an applicable document class, one operation producing 1,000 element identities reads each required `CreationGUID`, host GUID, and central ModelPath exactly once, performs one conversion/normalization/key derivation, and performs zero inapplicable host-property reads;
- one batch of 1,000 incoming identities resolves active-document evidence exactly once and performs no per-identity document-property reads;
- a later request receives a new snapshot rather than cached evidence;
- diagnostic enabled/disabled paths choose identical identity results;
- diagnostics do not persist keys, paths, GUIDs, titles, or filenames;
- deprecated `BimDocumentGuidSource.PathFallback` is never emitted by the resolver.

### Two-document live acceptance

With two documents open concurrently, test each applicable class and route:

- produce an element identity from document A;
- switch active document to B;
- call element information/parameters;
- call selection routes;
- call identity-based export routes;
- verify mismatch or unavailable is returned before element lookup;
- verify no element from B is selected, exported, or returned;
- switch back to A and verify the same identity succeeds.

The matrix must include:

- two different file-workshared models;
- a central/local pair that should match;
- a copied-central different-path pair that should not match;
- where safely available, a different model at the same former path;
- server and cloud fixtures when infrastructure is available;
- saved non-workshared project and family fixtures if probe-approved;
- unsaved and detached fail-closed fixtures.

Live acceptance also repeats `active_document`, `list_categories`, query, selection, and export smoke tests with diagnostics enabled and disabled. Source-contract tests alone cannot approve Revit host behavior.

## Deployment gate

Deployment requires:

- approved CreationGUID probe decision recorded in this file;
- unit and source-contract suites passing;
- `Rook` built before `RookBim`;
- exact deployed commit visible in `/bim/status`;
- fresh Revit restart;
- full document-class smoke matrix for available infrastructure;
- two-document resolution/selection/export acceptance;
- redacted JSONL and live report review;
- confirmation that file-workshared category enumeration remains successful.

The original unavailable customer model remains a desirable final reproduction but is not required to establish the two-document safety invariant in controlled fixtures.

## Rollback

This identity release rolls back independently of the Grasshopper lifecycle release.

A binary rollback would restore fail-open matching and is therefore unsafe while identity-based mutation/export routes remain available. Operational rollback must do one of:

- redeploy the corrected previous known-safe identity build, if one exists; or
- disable identity-based resolution, selection, and export capabilities until the corrected release is restored.

Do not partially roll back only the wire fields or only the comparator. Producers and consumers of `documentKey` must remain version-aligned.

## Approval and implementation-plan gate

This document may be committed and reviewed as a decision-gated specification. Its architecture, failure policy, class matrix, downgrade rules, cleanup boundary, and probe protocol are normative.

Before implementation planning proceeds beyond the probe task, this file must be amended with:

- the durable probe-report path;
- the observed class-by-class CreationGUID results;
- the approved key sources from the matrix;
- any explicitly unsupported classes;
- reviewer approval of the final key strategy.

Until then, the preferred file-workshared composite is a hypothesis under test, path-only durable matching is prohibited, and fail-closed behavior is the only authorized fallback.
