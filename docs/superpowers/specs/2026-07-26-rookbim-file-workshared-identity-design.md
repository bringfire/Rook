# RookBIM File-Workshared Document Identity Design

**Date:** 2026-07-26

**Status:** Approved design — outcome 2, class-limited composite; MCP and executable-policy amendment approved 2026-07-28

**Target:** `src/Rook` BIM contracts/policy, `src/RookBim` Revit adapter, and the closed Python MCP identity schema

**Deployment unit:** Separate RookBIM identity release after the decision gate passes

## Purpose

Replace RookBIM's server-only central-GUID assumption and fail-open document matching with one evidence-backed, host-specific document identity resolver.

The target invariant is:

> RookBIM resolves, selects, or exports an element identity only after trustworthy document evidence proves that the identity belongs to the active Revit document. Missing, conflicting, detached, unsupported, or incomparable evidence fails closed before `UniqueId` or `ElementId` lookup.

The live Revit 2024 `Document.CreationGUID` probe is complete and its class-limited result is approved below. Implementation planning may proceed only for the approved file-workshared and saved-project sources; every other document class remains fail closed unless this specification receives a later evidence-backed amendment.

Path-only identity is never approved for durable resolution. A path identifies a location, not a model; replacing a model at the same path would create an unsafe false positive.

## Linked incident

This design and [Rhino.Inside.Revit Grasshopper Document Lifecycle Design](2026-07-26-rir-grasshopper-document-lifecycle-design.md) came from the same Revit 2024.3 investigation but correct independent runtime boundaries.

Gated RookBIM diagnostics proved that a file-workshared model reached category item 380, then `Document.WorksharingCentralGUID` threw `Autodesk.Revit.Exceptions.InternalException` during identity projection. The Revit journal independently identified native `ADocument::getModelGUID_()`. The same current identity implementation also contains a preexisting safety defect: `DocumentMatches` treats an incoming identity without a persistent GUID as matching every active document. Neither defect is fixed by catching `InternalException`; both are replaced by this design.

The later Grasshopper/RiR incident concerns `GH_DocumentServer` registration and solver ownership. It has a separate specification, implementation plan, release, live report, and rollback path.

## Installed API evidence

The installed Revit 2024 API documents distinct properties with distinct applicability:

- `Document.CreationGUID`: the document's creation GUID from document history; introduced in Revit 2024.
- `Document.WorksharingCentralGUID`: the central GUID of a Revit Server model; it throws `InapplicableDataException` when the central model is not a qualifying server-based model.
- `Document.WorksharingProjectGUID`: the project GUID for a cloud-based central model.
- `Document.CloudModelGUID`: the GUID of a cloud model.
- `Document.GetWorksharingCentralModelPath()`: the central model path for a workshared document and invalid for a non-workshared document.
- `Document.IsDetached`: identifies a detached workshared document; detached documents may have empty title and path.

The current `SupportsWorksharingCentralGuid` implementation incorrectly treats a cloud model as supporting `WorksharingCentralGUID`. The new resolver removes that branch. The initial release emits versioned keys only for approved file-workshared and saved non-workshared project classes, explicitly retains the qualifying legacy Revit Server GUID rule, and treats cloud, family, unsaved, detached, and otherwise unsupported documents as unavailable.

## Goals

This design will:

- implement only the key sources approved by the completed `CreationGUID` probe;
- introduce versioned `documentKey` and `documentKeySource` fields;
- keep GUID-named fields restricted to actual GUID values;
- define identity behavior for every supported Revit document class;
- emit distinct typed key sources for approved file-workshared and saved-project documents only;
- centralize Revit document classification, evidence acquisition, normalization, key derivation, diagnostics, and comparison;
- acquire immutable document evidence once per operation and reuse it for every identity;
- degrade expected identity-property failures to unavailable evidence without failing producer routes;
- define byte-exact Windows path and key encoding;
- preserve the approved key fields across the closed MCP query-to-consumer boundary;
- provide one executable, Revit-free policy seam for classification, comparison, failure degradation, diagnostics parity, and per-operation read counts;
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
- identify a physical file instance, immutable revision, or content version;
- isolate same-lineage copies that later occupy the same canonical authoritative location;
- add new Revit Server, cloud, or saved-family versioned key sources without a later evidence-backed specification amendment;
- treat a process-local title, filename, or active-document position as identity;
- authorize resolution using raw `Path`, `DocumentPath`, `Title`, or `DocumentTitle`;
- use category, view, element, or model names as identity material;
- alter the separate RookBIM diagnostic sink architecture;
- change linked-document support beyond applying the same active-document gate before current linked-evidence handling;
- add Revit references to `src/Rook`;
- remove raw path fields from the existing wire contract without a separately versioned breaking-contract design;
- support Revit releases before 2024 in the first composite-key implementation;
- generalize the resolver into a repository-wide identity framework;
- add a new project, Revit reference, cache, registry, or cross-request identity state merely to make the policy testable;
- give the policy kernel a diagnostic observer, sink, context, or callback that could affect its decisions;
- duplicate key syntax or hash validation in Python;
- add a custom enum deserializer merely to rename transport-binding failures.

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

### Approved decision — outcome 2: class-limited composite

The completed redacted report is [2026-07-26-rookbim-creation-guid-result.md](../probes/2026-07-26-rookbim-creation-guid-result.md). It records all eleven required cases from Revit 2024.3 at probe commit `85c6df4f4f01dfd76a0a100dd4a201ce80ab96b2`; completion cleared the raw alias state. The reviewer accepted the report and approved outcome 2 on 2026-07-27.

The approved class matrix is:

| Document class or transition | Observed evidence | Approved disposition |
|---|---|---|
| File-workshared central and local | Central, local, and reopened local shared one creation alias and one central-path alias; local document-path evidence remained distinct and stable. | Approve `revit_creation_guid_central_path_v1`. |
| Copied central at a different location | The copy retained the central's creation alias but had a different central-path alias. | The approved file-workshared composite distinguishes the copy by location. |
| Saved non-workshared project | Creation and document-path aliases survived close/reopen. A different document saved to the same prior path retained the path alias but received a different creation alias. | Approve `revit_creation_guid_document_path_v1`. |
| Saved family | Creation was readable, nonempty, and stable on repeated reads; a saved document path was available. The required case set did not include a family-specific close/reopen or replacement pair. | Fail closed pending a later evidence gate. |
| Unsaved project and family | Creation was readable and stable, but no comparable saved path existed. | Fail closed. |
| Detached document | Creation matched the workshared lineage, but no comparable saved document path existed. | Fail closed; evidence is descriptive only. |
| Revit Server | New versioned-key evidence was unavailable. | Emit no new versioned key; retain only the explicit legacy rule below. |
| Cloud workshared | New versioned-key evidence was unavailable. | Fail closed; emit no new versioned key. |

The approved scope satisfies the observed file-workshared and saved-project criteria without authorizing a path-only downgrade. The specification is eligible for implementation planning only within this scope.

### Normative identity semantic

The two approved v1 composites identify **document lineage at a canonical authoritative location**. The authoritative location is the canonical central path for a file-workshared document and the canonical document path for a saved non-workshared project.

They do not identify a physical file instance, immutable revision, content version, or independently copied artifact. The probe proved that a copied central retains the original `CreationGUID`; Autodesk likewise defines `CreationGUID` as document-history identity in [Revit 2024 API changes](https://help.autodesk.com/view/RVT/2024/ENU/?caas=caas%2Fblog%2Fthebuildingcoder.typepad.com%2Fblog%2F2023%2F04%2Fwhats-new-in-the-revit-2024-api.html) and documents in the [Revit API FAQ](https://help.autodesk.com/cloudhelp/2025/CHS/Revit-API/files/Revit_API_Developers_Guide/Revit_API_Revit_API_Developers_Guide_FAQ_html.html) that element UniqueIds can be duplicated when one document is created by copying another.

Consequently, a same-lineage copy that later occupies the same canonical authoritative location compares equal to the earlier document by design. That equivalence is accepted for Rook's active-document authorization boundary. The acceptance suite must prove all three deliberate outcomes:

- same lineage at the same canonical authoritative location compares equal;
- same lineage at a different canonical authoritative location compares unequal;
- different lineage at the same canonical authoritative location compares unequal.

If a future capability requires physical-copy, immutable-revision, or content-version isolation, these v1 composites are insufficient. That capability requires a separately approved identity source, such as an external identity registry or a model-stored identifier, with its own versioned contract and migration design.

## Wire contract

### New fields

`BimDocumentIdentity` gains:

- `DocumentKey` (`documentKey`): a versioned opaque string or `null`;
- `DocumentKeySource` (`documentKeySource`): a closed typed source.

`BimElementIdentity` gains:

- `DocumentKey` (`documentKey`): copied from the owning document identity;
- `DocumentKeySource` (`documentKeySource`): copied from the owning document identity.

Initial-release key-source values are exactly:

- `revit_creation_guid_central_path_v1`;
- `revit_creation_guid_document_path_v1`;
- `unavailable`.

No production enum branch, payload encoder, parser, or resolver branch is added to reserve a future Revit Server, cloud, or saved-family source. Such a source requires a later evidence-backed contract amendment. The version is part of each approved source and key prefix so normalization or evidence changes cannot silently compare under the old contract.

### MCP identity boundary

The Python MCP identity schema is closed with `additionalProperties: false`, so the managed wire cutover and MCP schema cutover are one deployment invariant. `mcp_server/src/rook/server.py` adds these optional properties to the existing identity object:

- `documentKey`: `string | null`;
- `documentKeySource`: one of `revit_creation_guid_central_path_v1`, `revit_creation_guid_document_path_v1`, or `unavailable`.

Neither property is added to the MCP `required` list. Existing legacy envelopes that contain the currently required `documentGuidSource` therefore remain schema-valid. Schema compatibility does not authorize them: a legacy envelope without trustworthy comparable evidence still fails closed in the managed resolver.

Python performs no key-prefix, length, hexadecimal, source/prefix, GUID, or downgrade validation. It admits only the closed source strings above and forwards the identity dictionary unchanged. Unknown `documentKeySource` strings may fail at transport binding with HTTP 400; no custom enum converter is added merely to translate that failure to `document_identity_invalid`. Valid enum values paired with malformed or incoherent evidence reach the managed policy and return `document_identity_invalid` as defined below.

Tests must prove exact dictionary forwarding, with key names and string values unchanged, through all four identity consumers:

- element information;
- element parameters;
- selection;
- identity-list export.

The MCP cutover changes only the shared identity schema and its focused tests. It does not add a Python identity parser, normalizer, cache, or policy implementation.

### Key representation

Keys are opaque identifiers, not GUID fields. Each uses a source-specific prefix and lowercase SHA-256 of an unambiguous canonical payload.

Examples:

```text
file-document-v1:<64 lowercase hex>
saved-document-v1:<64 lowercase hex>
```

Payloads use a fixed ASCII domain/version label, NUL separators, lowercase `D`-format GUID text, and the normalized path where required. Length, prefix, character set, and source/prefix pairing are validated before comparison.

### Legacy GUID fields

`Guid` and `DocumentGuid` continue to contain only actual Revit GUID values or `null`. A path hash or composite hash is never stored in either field.

`BimDocumentGuidSource.PathFallback` remains temporarily for wire compatibility but is deprecated and is not emitted by the new resolver. The resolver treats an incoming legacy `path_fallback` GUID source as incomparable, because no GUID-named value can correctly represent that evidence.

The initial release explicitly retains one legacy rule for a qualifying Revit Server document: only when the incoming identity has no `documentKey`, its actual legacy `WorksharingCentralGUID` may compare with the active server document's actual `WorksharingCentralGUID`. Revit Server emits no new `documentKey` or versioned key source. Cloud and every other class do not call `WorksharingCentralGUID`; cloud identities fail closed and emit no new or legacy comparable key.

`CreationGUID` is key material only. It is never projected into legacy `Guid` or `DocumentGuid` for file-workshared or saved-project sources. Saved-family identity is unavailable. Those legacy fields are `null` unless the explicit qualifying Revit Server legacy rule applies.

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
- Revit Server `WorksharingCentralGUID` reads only for the explicitly retained no-key legacy comparison;
- worksharing central `ModelPath` acquisition;
- user-visible path conversion and normalization;
- key derivation and validation;
- legacy GUID projection;
- document identity DTO construction;
- comparison and closed failure results;
- diagnostic stages for every production read.

No caller directly reads these GUID/path properties for identity. The current `GetWorksharingCentralGUID`, `SupportsWorksharingCentralGuid`, and boolean `DocumentMatches` branches are deleted after replacement coverage exists.

### Two-layer resolver boundary

The resolver has exactly two layers:

1. A small Revit-free policy kernel in `src/Rook` owns classification order, approved key selection, evidence coherence, comparison, and closed outcomes.
2. A thin adapter in `src/RookBim` owns Autodesk types, actual Revit reads, expected-exception classification, display-field projection, and diagnostic observation.

The policy receives a closed set of lazy reader callbacks. Each callback returns either a typed success value or a bounded unavailable result and retains no `Exception`. The policy invokes each required identity reader at most once per operation. Counting fakes can therefore execute the real classification and comparison policy in `Rook.Tests` without loading Revit.

Only the minimum policy input/result/read-helper surface is public, because `RookBim` is a separate optional assembly. These types live in the BIM contract namespace but are not serialized DTOs, routes, extension points, or a promise of third-party identity providers.

The core also supplies one small Revit-free read helper. It accepts one effective read delegate plus an expected-exception predicate, converts an expected exception into the same bounded unavailable result, retains no exception, and rethrows an unexpected exception. The Revit adapter selects either its diagnostic-wrapped getter or direct getter before passing that one delegate to the helper. Tests use synthetic exceptions and the existing diagnostic probe to prove equal enabled/disabled results. The Revit adapter supplies the actual Revit exception predicate and property delegates. No Revit type enters `src/Rook`, and no new test project or source-linked production copy is introduced.

Diagnostics remain outside the policy kernel. For an enabled request, the adapter observes a production read best-effort and then converts an expected exception to unavailable evidence. For a disabled request, it executes the same getter directly and applies the same conversion. The policy receives neither a diagnostic context nor any observer, sink, delegate wrapper, or global flag capable of changing its decision. Executable tests run equivalent enabled-style and disabled-style reader results through the policy and require identical classification, key, comparison, and error outcomes.

This seam is BIM-specific. It is not a general host-property framework, dependency-injection container, cache, event stream, or telemetry abstraction.

### Fail-closed classification sequence

Identity classification uses this exact branch order:

1. Read `IsDetached` and `IsWorkshared`. If either required read is unavailable, identity classification is unavailable and no class-specific or key-material reader runs.
2. If detached is true, identity classification is unavailable and no key-material reader runs.
3. If workshared is true, read `IsModelInCloud`. If unavailable, stop identity classification. If true, classify cloud/unavailable and stop.
4. Only after those base discriminators succeed and `IsWorkshared == true`, read the central `ModelPath` once. Never read it for a non-workshared document. If acquisition or path-kind classification is unavailable, stop identity classification. A cloud path is cloud/unavailable; a server path may enter only the retained legacy server branch; a file path may enter only the approved file-workshared branch. No outcome falls through to saved-project derivation.
5. If workshared is false, read `IsFamilyDocument`. If unavailable, stop identity classification. A family document is unavailable in this release. A non-family project with no usable `PathName` is unsaved/unavailable; otherwise it may enter only the approved saved-project branch.
6. Once a branch is selected, any unavailable required `CreationGUID`, server GUID, conversion, canonicalization, or key-construction result makes that branch unavailable. It never retries another class or weaker source.

“Stop” above applies to identity classification and key-material reads. Independent compatibility/display reads such as title and document path may still execute best-effort for producer responses. Their success cannot resume classification, select a key source, or authorize comparison.

### Operation-scoped evidence ownership

Each Revit work item resolves one immutable `RevitDocumentIdentityEvidence` snapshot inside the valid Revit API context before producing or consuming identities. The snapshot contains the owning live `Document` wrapper as a non-serialized scope value, document classification, selected key/source or unavailable reason, approved legacy projection, and already-read DTO display fields. It contains no lazy Revit getters, delegates, raw exceptions, or cross-request mutable state.

The operation passes that snapshot explicitly to document and element identity projection. Every element identity in a query/list/export response reuses the same snapshot; projection never calls back into document classification, GUID, ModelPath, normalization, or hashing. Element projection fails closed unless `IsSameDocument(element.Document, evidence.Owner)` succeeds; the helper's only non-null comparison is Revit `Document.Equals`, because Revit may return distinct managed wrappers for the same native document. This same-operation ownership check is separate from durable document-key authorization.

Identity-consuming operations likewise resolve the active-document snapshot once, compare every caller-supplied or persisted identity against that same snapshot, and complete all document-identity validation before any selection, mutation, export, `UniqueId`, or `ElementId` lookup. A batch never recomputes active-document evidence per identity and never partially acts on identities before a later document-evidence failure.

The snapshot lifetime is exactly one operation. It is not stored in static state, `AsyncLocal`, a global dictionary, a `Document`-keyed cache, or a handler field, and it is not reused by a later request. Cross-request or document-lifecycle caching requires a separate invalidation design and is outside this specification.

### Trusted live-element boundary

Caller-supplied or persisted identities are untrusted wire evidence and always pass through document-key comparison. Live `Autodesk.Revit.DB.Element` references returned by a Rook-owned query against the captured `Document` in the same Revit operation are already trusted operation state; they must not be serialized and immediately re-resolved merely to authorize their continued use.

`src/RookBim` introduces an internal query-execution result containing both the public `BimQueryElementsResult` projection and the corresponding ordered live `Element` references. The live references:

- never enter `src/Rook` contracts or any shared DTO;
- never cross the Revit API-context boundary;
- are never serialized, persisted, cached, placed in deferred work, or reused by another request;
- are accepted only when the fail-closed `IsSameDocument(element.Document, capturedDocument)` guard succeeds within that operation using Revit `Document.Equals`.

Selector export consumes this internal live list directly. Preset resolution carries the same live references across its same-operation category queries and deduplicates them within the captured document by `ElementId.Value`, not by serializing a document GUID and resolving the identity again. Public query responses still project wire summaries using the operation-scoped document-evidence snapshot; an unavailable document key therefore produces null keys without discarding the live references.

Identity-list export remains a separate untrusted path: it compares every supplied identity to the active snapshot and fails closed before lookup or export when evidence is unavailable, invalid, or mismatched. Selector and preset exports are active-document queries rather than identity authorization, so they remain available for unsaved, detached, or probe-rejected document classes when their ordinary query/export preconditions pass. This exception does not authorize any caller-provided identity and cannot escape the same operation.

### Identity-read failure containment

The adapter wraps each policy-invoked classification, GUID, ModelPath, conversion, and normalization read independently; the policy's classification sequence decides which readers are invoked. A closed availability wrapper converts expected data/applicability failures into unavailable evidence. Its Revit exception allowlist includes `InapplicableDataException`, `InvalidOperationException`, `InternalException`, `InvalidObjectException`, and the Revit argument/null exceptions documented by an invoked conversion API. Path/key construction also treats `System.ArgumentException`, `NotSupportedException`, `PathTooLongException`, `System.Security.SecurityException`, `System.Text.EncoderFallbackException`, and `System.Security.Cryptography.CryptographicException` as unavailable evidence. The adapter does not catch `Exception` indiscriminately; programming defects and process-fatal exceptions remain subject to the operation-level error boundary.

If a required identity input fails with an expected exception, the snapshot records a bounded unavailable reason, emits `DocumentKey = null`/`DocumentKeySource = unavailable`, and retains no exception object. Other independent DTO evidence may still be read. Diagnostics observe the exact failed stage and bounded exception facts but do not change the returned snapshot.

Identity-producing routes—including `active_document`, `list_categories`, and query/list responses—continue their otherwise successful work and return HTTP 200 with `documentKey: null` when trustworthy identity evidence is unavailable. Element identities produced by that operation also carry a null document key. Routes consuming caller-supplied or persisted identities fail closed with `document_identity_unavailable` before element lookup or side effects. Thus failure of `CreationGUID`, ModelPath, a host-specific GUID, conversion, normalization, or hashing cannot recreate the original route-wide `list_categories` failure.

## Document-class matrix

| Document class | Required evidence | Preferred authoritative key | Unsupported/failure behavior |
|---|---|---|---|
| File-workshared central | Not detached; suitable `CreationGUID`; absolute normalized file central `ModelPath` | `revit_creation_guid_central_path_v1` | `document_identity_unavailable` |
| File-workshared local | Not detached; same suitable `CreationGUID` as central; same normalized central `ModelPath` | Same composite as its central | `document_identity_unavailable` |
| Revit Server central/local | Qualifying actual legacy `WorksharingCentralGUID`, only when no incoming `documentKey` exists | No new versioned key; `documentKeySource=unavailable` | Retained legacy comparison only; otherwise `document_identity_unavailable`; never fall back to cloud/file reads |
| Cloud workshared | Cloud classification only | `unavailable` | `document_identity_unavailable`; emit no new key and never call `WorksharingCentralGUID`, `WorksharingProjectGUID`, or `CloudModelGUID` for identity |
| Saved non-workshared project | Suitable `CreationGUID`; absolute normalized `PathName` | `revit_creation_guid_document_path_v1` | `document_identity_unavailable` when required evidence cannot be produced |
| Saved family document | Family classification | `unavailable` | `document_identity_unavailable`; no saved-family key derivation |
| Unsaved project | No durable path | `unavailable` | Identity may be returned for display, but resolution/selection/export by identity fails closed |
| Unsaved family | No durable path | `unavailable` | Same fail-closed behavior |
| Detached document | Rejected before key derivation | `unavailable` | `document_identity_unavailable`; never use retained central/path/GUID values |

Linked RVT documents do not bypass this matrix. The active host document must match first; current linked-evidence policy then applies separately.

The initial release emits a versioned key only for the two approved sources. It adds no production source value or derivation branch for Revit Server, cloud, or saved families. Operations authorized by caller-supplied or persisted identities fail closed for cloud, saved-family, unsaved, detached, and otherwise unavailable evidence. Same-operation selector/preset queries follow the trusted live-element boundary instead.

## Canonicalization and key derivation

### File central path

For a workshared, non-detached, non-cloud document, the adapter obtains `GetWorksharingCentralModelPath()` once and classifies the returned `ModelPath`. It rejects null or unclassifiable paths, stops on cloud, enters the legacy branch on server, and converts only a qualifying file path exactly once with `ModelPathUtils.ConvertModelPathToUserVisiblePath(modelPath)` before passing it to the shared Windows canonicalizer below.

The Windows canonicalizer is byte-contract code and executes this exact sequence for both converted central paths and saved `Document.PathName` values:

1. Reject null, empty, whitespace-only, or embedded-NUL input. Do not trim the input.
2. Replace every `/` (U+002F) with `\` (U+005C).
3. Reject device/NT namespace prefixes `\\?\`, `\\.\`, and `\??\` using ordinal-ignore-case comparison.
4. Accept only a drive-absolute form beginning with `[A-Za-z]:\`, or a UNC form beginning with `\\` and containing non-empty server and share segments. Reject relative, root-relative, drive-relative, URI, and incomplete UNC forms before calling `Path.GetFullPath`.
5. Call `System.IO.Path.GetFullPath` exactly once to collapse `.`/`..` segments and redundant separators. Replace any `/` in its result with `\` and repeat the device/absolute-form validation.
6. Obtain `Path.GetPathRoot` and reject a null/empty or incomplete root. A drive root has the canonical form `C:\` and retains its final separator. A UNC share root has the canonical form `\\SERVER\SHARE` with no final separator. Remove trailing `\` from every UNC result and from non-root drive paths; if a drive result equals its root, preserve the one root separator.
7. Apply `ToUpperInvariant()` to the entire resulting string. Apply no Unicode normalization and perform no trimming.

The canonical output therefore always uses `\`, has an uppercase invariant representation, preserves a drive-root separator, and omits a UNC-share-root separator. The resolver performs no filesystem existence lookup, symlink/junction resolution, 8.3-name expansion, network access, or mapped-drive-to-UNC conversion.

Golden canonical-text/UTF-8 vectors are normative:

| Input | Canonical text | UTF-8 bytes (hex) |
|---|---|---|
| `C:\` | `C:\` | `433a5c` |
| `c:/Models/../A.rvt` | `C:\A.RVT` | `433a5c412e525654` |
| `\\server\share` | `\\SERVER\SHARE` | `5c5c5345525645525c5348415245` |
| `\\server\share\` | `\\SERVER\SHARE` | `5c5c5345525645525c5348415245` |
| `\\server\share\folder\..\` | `\\SERVER\SHARE` | `5c5c5345525645525c5348415245` |

Mapped-drive and UNC representations can therefore produce a safe false negative. They can never authorize a different model because the key also requires the probe-approved `CreationGUID`.

### Saved non-workshared project path

This class uses absolute normalized `Document.PathName`, not `GetWorksharingCentralModelPath`. Saved families do not enter key derivation in the initial release.

### Source-specific payloads

Conceptual payloads are:

```text
rookbim:file-workshared:v1\0<creation-guid>\0<normalized-central-path>
rookbim:saved-project:v1\0<creation-guid>\0<normalized-document-path>
```

GUID payload values use lowercase `D` format. Each `\0` above is one NUL byte (`0x00`) between fields. The complete payload string is encoded with strict UTF-8 without a BOM; invalid UTF-16 input is rejected rather than replacement-encoded. SHA-256 runs over those exact bytes, and the final wire key is the source prefix plus exactly 64 lowercase ASCII hexadecimal characters. Raw payloads are not persisted in diagnostics.

## Matching and downgrade prevention

The resolver replaces `DocumentMatches` with a closed result such as:

- `Match`;
- `Mismatch`;
- `Unavailable`;
- `InvalidEvidence`.

The comparison order is normative.

### Validation precedence and batch preflight

Every identity-consuming route applies this exact precedence:

1. A null identity or null batch entry returns `InvalidEvidence`.
2. Any linked evidence returns the existing `LinkedElementUnsupported` result. Linked evidence means `Linked == true`, any linked numeric identifier, or any supplied linked string field, including an empty or whitespace string.
3. Validate identity source plus key/source/legacy coherence using the table below.
4. Compare the coherent document evidence with the active operation snapshot.
5. Validate the element locator using the existing UniqueId-first and ElementId-fallback contract.
6. For a batch, complete steps 1–5 for every entry in input order before the first `GetElement`, selection change, export conversion, or file write. Only a wholly valid and document-matched batch proceeds to lookup; only a wholly resolved batch proceeds to side effects.

The first failing entry by input order and the first applicable rule above determine the response. An earlier valid entry never causes partial lookup or action before a later entry fails.

For the tables below, **absent** means null or omitted. Empty and whitespace strings are present and invalid unless a rule explicitly says otherwise. A **strong source** means one of the two approved versioned `documentKeySource` values. Coherence rows are evaluated from top to bottom.

| Incoming evidence | Coherence result |
|---|---|
| `Source` is not exactly `revit` | `InvalidEvidence` |
| Key absent; strong key source supplied | `InvalidEvidence` |
| Key empty/whitespace, malformed, unknown-version, or inconsistent with its strong source | `InvalidEvidence` |
| Key present; key source is `unavailable` | `InvalidEvidence` |
| Valid key/source; legacy GUID absent and legacy source `unavailable` | Proceed to strong comparison |
| Valid key/source plus any legacy GUID value or any legacy source other than `unavailable` | `InvalidEvidence` |
| Key absent; key source `unavailable`; legacy GUID absent; legacy source `unavailable` | `Unavailable` |
| Key absent; key source `unavailable`; valid non-empty actual GUID; legacy source `revit_persistent_guid` | Proceed to retained server comparison |
| Key absent; key source `unavailable`; nonblank legacy value; legacy source `path_fallback` | `Unavailable`; deprecated evidence is admitted by transport but never authorizes |
| Legacy GUID absent with `revit_persistent_guid` or `path_fallback` source | `InvalidEvidence` |
| Legacy GUID under `revit_persistent_guid` is empty, whitespace, malformed, or empty-GUID text | `InvalidEvidence` |
| Valid legacy GUID present with `unavailable` or another mismatched source | `InvalidEvidence` |

Unknown enum strings may be rejected by normal transport binding with HTTP 400 before this table runs. The implementation adds no custom deserializer to rename that boundary.

After coherence succeeds, document comparison is exact:

| Incoming comparable evidence | Active evidence | Result |
|---|---|---|
| Approved strong key/source | Same source and ordinal-equal valid key | `Match` |
| Approved strong key/source | Same source and different valid key | `Mismatch` |
| Approved strong key/source | Different approved strong source | `Mismatch` |
| Approved strong key/source | Required active evidence unavailable | `Unavailable` |
| Valid retained server GUID | Qualifying server GUID equal ignoring GUID text case | `Match` |
| Valid retained server GUID | Qualifying server GUID different | `Mismatch` |
| Valid retained server GUID | Active document conclusively belongs to a non-server class | `Mismatch` |
| Valid retained server GUID | Active server/classification evidence unavailable | `Unavailable` |

No path, title, locator, or later lookup can change these outcomes.

### Incoming versioned key present

1. Validate key syntax, source, version, and source/prefix agreement.
2. Resolve the active document using that exact supported source/version.
3. If the active document cannot produce comparable evidence, return `Unavailable`.
4. If values differ, return `Mismatch`.
5. If values match, require the legacy GUID to be absent and its source to be `unavailable`. Neither approved versioned source has a legacy GUID projection, so any other legacy value/source combination is conflicting evidence.
6. If supplied evidence conflicts or cannot be validly projected for that source, return `InvalidEvidence`.
7. Only a fully consistent result is `Match`.

A mismatching, malformed, unknown-version, unsupported, or unverifiable versioned key never falls back to a legacy GUID, raw path, title, `UniqueId`, or `ElementId`.

### No incoming versioned key

Legacy comparison is allowed only when no stronger key was supplied.

- The initial release explicitly retains comparison of a qualifying legacy Revit Server identity's actual persistent GUID with the active server document's actual central GUID.
- A coherent nonblank `path_fallback` legacy envelope remains transport-compatible but returns `Unavailable`; malformed or value/source-incoherent legacy evidence returns `InvalidEvidence`.
- Legacy cloud/file/unavailable identities without an approved comparable key fail closed.
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
- server central GUID, only for the retained legacy comparison;
- central ModelPath;
- saved-project document path;
- path conversion/normalization result;
- key-source selection;
- comparison outcome.

Diagnostics record stage, outcome, detail code, exception type, and HResult under existing bounds. They never persist:

- GUID values;
- document keys;
- raw or normalized paths;
- titles or filenames;
- request identities.

Expected identity-read exceptions follow the failure-containment contract above whether diagnostics are enabled or disabled: producing routes continue with unavailable evidence, while routes consuming caller-supplied or persisted identities fail closed. Optional diagnostic-only probes catch locally and never affect the snapshot. The diagnostic flag must not select a different key, matching result, HTTP status, or route-success outcome.

## Cleanup and doctrine

The implementation replaces rather than layers over obsolete behavior. It removes or supersedes:

- the cloud branch in `SupportsWorksharingCentralGuid`;
- universal use of `WorksharingCentralGUID` as document identity;
- scattered direct document-identity property reads;
- boolean `DocumentMatches`;
- the unconditional `true` result for missing persistent GUID evidence;
- selector-export serialization/re-resolution of same-operation query results;
- preset serialization/re-resolution and document-GUID-based deduplication of same-operation live elements;
- tests requiring `PathFallback` to remain absent from executable identity design;
- tests that treat unavailable document evidence as a universal match;
- Phase 1 language declaring `path_fallback` only diagnostic/non-stable without describing the new versioned key contract.

The Phase 1 design receives a superseded notice linking here. Historical context remains readable, but its old rule no longer governs the new `documentKey` contract.

Compatibility fields retained intentionally are not behavior owners. No new compatibility resolver runs in parallel with `RevitDocumentIdentityResolver`.

Cleanup is limited to document identity production/comparison and removal of the two diagnosed same-operation export round-trips. It does not authorize unrelated export, selection, category, link, or diagnostic refactoring.

## Commit and deployment boundaries

This specification has its own implementation plan and release, independent of the Grasshopper lifecycle design.

Expected reviewable boundaries are:

1. Operator-assisted CreationGUID probe and durable redacted report; update this specification with the approved decision.
2. Pure key contract plus the Revit-free policy/read-result seam and executable tests, kept behavior-neutral and unused by production routes.
3. One production resolver cutover that adds managed contract fields, updates the closed MCP identity schema, centralizes all document classes behind the Revit adapter and policy, removes fail-open matching and incorrect GUID branches, carries trusted query elements internally for selector/preset export, replaces obsolete tests, and updates doctrine.

Step 1 is complete and reviewed. Implementation planning may now define steps 2 and 3 for the approved initial-release scope. Any preparatory code remains unused and behavior-neutral until the resolver cutover, and no identity deployment occurs before the implementation-plan and live-acceptance gates pass.

`src/RookBim/RookBim.csproj` remains Revit-specific and must build after `src/Rook/Rook.csproj`. Core contracts, optional module, and Python MCP schema stay version-aligned in the atomic cutover. The deployed `/bim/status` commit must identify the exact code under acceptance.

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

- the exact initial-release source set and wire names: `revit_creation_guid_central_path_v1`, `revit_creation_guid_document_path_v1`, and `unavailable`;
- MCP identity schemas expose optional `documentKey` and `documentKeySource`, retain `additionalProperties: false`, retain the existing legacy required fields, and reject unknown key-source strings through ordinary schema/binding behavior;
- MCP forwards a representative strong identity dictionary without dropping, renaming, normalizing, or recomputing either new field through element information, element parameters, selection, and identity-list export;
- Python contains no duplicate key regex, hash, prefix/source, GUID-coherence, or downgrade policy;
- absence of reserved Revit Server, cloud, and saved-family production source values, payload encoders, parsers, and derivation branches;
- GUID fields reject/non-emit hashes;
- `CreationGUID` is never projected into legacy `Guid`/`DocumentGuid` for file-workshared or saved-project sources;
- key prefix/source/version validation;
- golden byte/hash vectors for both approved source payloads;
- byte-exact Windows case and separator normalization for drive and UNC paths;
- drive roots preserve one trailing separator while UNC share roots omit it;
- `\\server\share`, `\\server\share\`, and `\\server\share\folder\..\` produce the exact same canonical text and UTF-8 bytes shown above;
- rejection of empty, relative, drive-relative, root-relative, URI, incomplete UNC, embedded-NUL, and device-namespace paths;
- strict UTF-8 without BOM and lowercase 64-character SHA-256 output;
- mapped/UNC differences produce non-match, not normalization guesses;
- counting fake readers execute the production policy and prove each required identity read occurs at most once per operation;
- `ModelPath` is read exactly once only for a successfully classified workshared document and never for a non-workshared document;
- unavailable `IsDetached`, `IsWorkshared`, `IsModelInCloud`, `IsFamilyDocument`, or ModelPath classification stops identity/key reads and never falls through to another class;
- independent display reads may continue after identity classification becomes unavailable but cannot alter its result;
- synthetic expected reader exceptions become bounded unavailable results with no retained exception, while unexpected exceptions are rethrown;
- equivalent enabled-style and disabled-style adapter results produce identical policy classification, key, comparison, and error outcomes, with diagnostics absent from the policy API;
- the retained Revit Server legacy comparator reads only the actual `WorksharingCentralGUID`, runs only when no incoming `documentKey` exists, and emits no new versioned key;
- cloud classification emits unavailable identity and calls none of `WorksharingCentralGUID`, `WorksharingProjectGUID`, or `CloudModelGUID` for identity;
- file central/local code uses the approved composite only;
- saved projects use the approved document-path composite;
- saved families, unsaved documents, detached documents, and cloud documents fail closed;
- every matrix row has a test;
- same lineage at the same canonical authoritative location compares equal by design;
- same lineage at a different canonical authoritative location compares unequal;
- different lineage at the same canonical authoritative location compares unequal;
- strong key match/mismatch/unavailable behavior;
- unknown key version fails without downgrade;
- malformed key fails without downgrade;
- whitespace key, key with `unavailable` source, and missing key with a strong source are invalid;
- conflicting key and legacy GUID is invalid;
- missing, whitespace, malformed, empty, source-incoherent, and deprecated path-fallback legacy cases match the normative coherence table;
- legacy GUID comparison runs only when no document key is supplied;
- raw path/title never participates in authorization;
- element `UniqueId` and `ElementId` lookups occur only after `Match`;
- expected Revit identity exceptions, including `InternalException`, produce unavailable snapshots rather than route-wide producer failures;
- `active_document`, `list_categories`, and query/list producers remain HTTP 200 with null document keys when evidence is unavailable;
- consumers return HTTP 409 `document_identity_unavailable` or HTTP 400 `document_identity_invalid` as specified, before lookup or side effects;
- for an approved composite class, one operation producing 1,000 element identities reads the required `CreationGUID` and applicable central/document path exactly once, performs one conversion/normalization/key derivation, and performs zero inapplicable host-property reads;
- for a qualifying legacy Revit Server comparison, one batch reads the active actual central GUID exactly once and performs no new-key derivation;
- one batch of 1,000 incoming identities resolves active-document evidence exactly once and performs no per-identity document-property reads;
- validation precedence is null, linked evidence, coherence, document comparison, and locator validation;
- a null batch entry, linked evidence in any entry, or later invalid identity prevents every `GetElement` and side effect in the batch;
- explicit identity-list export with unavailable evidence fails closed before `GetElement` or export work;
- selector export with unavailable identity evidence consumes same-operation live elements directly and remains available when ordinary query/export preconditions pass;
- preset export with unavailable identity evidence carries and deduplicates same-operation live elements without `DocumentIdentity`, `ElementIdentity`, or `Resolve` round-trips;
- live elements never appear in shared DTOs, serialized output, caches, deferred work, or a later operation;
- a live element whose `Document` is not the captured document is rejected before internal use;
- a later request receives a new snapshot rather than cached evidence;
- diagnostic enabled/disabled paths choose identical identity results;
- diagnostics do not persist keys, paths, GUIDs, titles, or filenames;
- deprecated `BimDocumentGuidSource.PathFallback` is never emitted by the resolver.

### Two-document live acceptance

With two documents open concurrently, test each applicable class and route:

- produce an element identity from document A through the MCP query tool;
- switch active document to B;
- pass that exact returned dictionary through MCP element information and parameters;
- pass it through MCP selection;
- pass it through MCP identity-list export;
- verify mismatch or unavailable is returned before element lookup;
- verify no element from B is selected, exported, or returned;
- switch back to A and verify the same identity succeeds.

The matrix must include:

- two different file-workshared models;
- a central/local pair that should match;
- a copied-central different-path pair that should not match;
- a same-lineage copy later occupying the same canonical location, which should match by design;
- a different-lineage model at the same former path, which should not match;
- Revit Server and cloud fixtures when infrastructure is available, proving legacy-only server behavior and cloud fail-closed behavior;
- a saved non-workshared project fixture;
- a saved-family fail-closed fixture;
- unsaved and detached fail-closed fixtures.

The same-location cases use this exact disposable sequence because two physical files cannot simultaneously occupy one canonical path:

1. Open the original at canonical path P and capture an MCP query identity.
2. Close the document and Revit file handle.
3. Place a same-lineage copy at P, reopen P, and verify the original identity compares equal and completes all four MCP consumer round trips.
4. Close the document and file handle again.
5. Replace P with a different-lineage document, reopen P, and verify the original identity fails before lookup or side effects through all four consumers.

This sequence documents the accepted lineage-plus-location semantic; it is not a physical-copy isolation claim.

Live acceptance also repeats `active_document`, `list_categories`, query, selection, and export smoke tests with diagnostics enabled and disabled. Source-contract tests alone cannot approve Revit host behavior.

The final Revit journal scan must contain no new `ADocument::getModelGUID_()` failure or “internal error” attributable to a file-workshared operation. It must also prove that file-workshared routes never invoke the server central-GUID stage.

For every available class with unavailable identity evidence, live acceptance distinguishes the two export trust paths: selector/preset export succeeds from same-operation query elements, while identity-list export returns `document_identity_unavailable` before element lookup or file output.

## Deployment gate

Deployment requires:

- approved CreationGUID probe decision recorded in this file;
- managed policy/contract, optional-module source-contract, and focused MCP suites passing;
- `Rook` built before `RookBim`;
- exact deployed commit visible in `/bim/status`;
- fresh Revit restart;
- full document-class smoke matrix for available infrastructure;
- two-document resolution/selection/export acceptance;
- all four MCP query-to-consumer round trips and the exact close/copy/replace/reopen sequence;
- redacted JSONL and live report review;
- confirmation that file-workshared category enumeration remains successful and the Revit journal contains no new file-workshared server-GUID failure.

The original unavailable customer model remains a desirable final reproduction but is not required to establish the two-document safety invariant in controlled fixtures.

## Rollback

This identity release rolls back independently of the Grasshopper lifecycle release.

A binary rollback would restore fail-open matching and is therefore unsafe while identity-based mutation/export routes remain available. Operational rollback must do one of:

- redeploy the corrected previous known-safe identity build, if one exists; or
- disable identity-based resolution, selection, and export capabilities until the corrected release is restored.

Do not partially roll back only the managed wire fields, MCP schema, policy, Revit adapter, or comparator. Producers, Python transport, and consumers of `documentKey` must remain version-aligned.

## Approval and implementation-plan gate

The reviewer approved outcome 2, class-limited composite, on 2026-07-27. The durable report, observed matrix, identity semantic, approved sources, and fail-closed classes are recorded above.

On 2026-07-28 the reviewer approved the KISS two-layer amendment: one Revit-free policy kernel, one diagnostic-owning Revit adapter, the two optional MCP fields, the complete coherence/precedence contract, and the expanded MCP/live acceptance gate. Implementation planning must include `mcp_server/src/rook/server.py` and `mcp_server/tests/test_rookbim_mcp_tools.py` in the atomic production cutover. A plan that declares MCP unchanged is not executable.

Implementation planning is authorized only for:

- `revit_creation_guid_central_path_v1` on file-workshared central/local documents;
- `revit_creation_guid_document_path_v1` on saved non-workshared projects;
- the explicit no-key legacy Revit Server GUID comparison;
- fail-closed behavior for saved families, unsaved projects/families, detached documents, cloud documents, and otherwise unavailable evidence.

No new Revit Server, cloud, or saved-family versioned key is authorized. Path-only durable matching remains prohibited. Expanding the emission set or requiring physical-copy/revision isolation reopens the evidence and specification gate.

The Grasshopper lifecycle plan's prerequisite is satisfied: the temporary CreationGUID probe was completed, reviewed to this decision, and rolled back before Grasshopper deployment. That satisfaction does not couple the two implementation releases.
