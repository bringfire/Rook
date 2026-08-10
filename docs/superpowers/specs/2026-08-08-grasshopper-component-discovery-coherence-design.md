# Grasshopper Component Discovery Coherence Design

**Status:** Implementation-ready production contract; awaiting independent review
**Date:** 2026-08-08
**Amended:** 2026-08-09
**Production baseline:** `a0f2a12e3388f069e51dbaa8e30c646983c26d76`
**Branch:** `codex/grasshopper-component-discovery-coherence-production-design`

## Purpose

Rook already exposes Grasshopper's live registered component catalog and SDK-backed
component metadata. The missing quality is a coherent ownership chain between search,
type identity, metadata lookup, and creation.

This contract establishes that chain:

```text
Grasshopper native retrieval proposes candidates
-> proxy-owned identity distinguishes component types
-> source-kind provenance describes the selected type
-> temporary-instance metadata describes its implementation and ports
-> the selected component-type GUID enters validated mutation
-> existing T* and C* identities own graph execution
```

Grasshopper remains authoritative for installed component registration, native search,
aliases, native relevance scores, proxy identity, and SDK metadata. Rook owns public
filtering, deterministic tie-breaking, correlation, compatibility fields, and truthful
failure projection. Knowledge owns none of those facts.

## Evidence authority

The production decisions in this contract are based on two independently reviewed,
read-only qualifications. They must not be repeated as part of implementation.

### Native discovery qualification

Report:

```text
docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md
```

Retained evidence:

```text
native-discovery.json SHA-256
254A9BF5A8EEE5DCCA72A37AD08DF20EDF63271F55E2F14AC4587BC180481988
```

It established:

- complete `FindObjects()` candidate acquisition remained below 16 ms across every
  qualified call on a live catalog containing 1,890 proxies;
- native ordering and weights were stable across repeated calls;
- canonical components ranked first for the fixed searches;
- category filtering must occur before the public limit;
- native search excluded only hidden legacy matches in the qualified cases;
- installed third-party and `.ghuser` components remained discoverable;
- public exact-name identity cannot use `FindObjectByName()` because it collapses
  duplicates;
- 53 non-obsolete exact-name duplicate groups existed, at least 33 with multiple
  non-hidden candidates.

### User-object provenance qualification

Report:

```text
docs/superpowers/reports/2026-08-09-grasshopper-user-object-provenance-qualification-v2.md
```

Retained evidence:

```text
user-object-provenance.json SHA-256
E7BC4124D1029D9F50721FB45B3E1079317CDC1901A0332B635532681CCE04BD

invoke-result.json SHA-256
DCA890C23199698AFFE97DC8A43867CE9E91295A7020DFBE6A51B24332104A20
```

It established:

- a `.ghuser` proxy GUID identifies that user object in the current installation but is
  not promised to be portable across machines;
- exact user-object path and content fingerprint distinguish installed user-object
  identities without archive parsing or package inference;
- `BaseGuid`, temporary `ComponentGuid`, runtime type, and runtime assembly describe the
  shared execution implementation, not the package that supplied the `.ghuser`;
- compiled `.gha` components and `.ghuser` components require distinct provenance
  variants.

The evidence does not establish package, author, family, or package-version identity for
`.ghuser` files. Folder names remain environmental observations, not public package
labels.

## Scope

The production correction is limited to:

- native-ranked `gh_library` search with a separate catalog-browse branch;
- complete filtering before limiting and deterministic tie-breaking;
- compact search-level source-kind disclosure;
- GUID-safe and duplicate-name-safe `gh_batch_component_info` behavior;
- closed compiled and user-object provenance variants for selected metadata;
- exact selector and per-item outcome correlation;
- `gh_library.exact` parity through direct `ToolDispatcher` dispatch;
- suppression of unrelated knowledge hints for `gh_library` and
  `gh_batch_component_info`.

The frozen Opus control remains an unchanged-surface affordance audit that must run under
separate authorization before production deployment. It does not choose the search
algorithm and cannot invalidate the qualification evidence.

## Explicit non-goals

This slice adds no:

- embeddings, vector retrieval, semantic reranking, or reciprocal-rank fusion;
- custom alias catalog, synonym table, fuzzy matcher, or morphology engine;
- knowledge-store identity authority, recipe retrieval, or knowledge cleanup;
- DSPy optimization;
- harvested component registry or curated core-component allowlist;
- new component shorthand family;
- semantic-graph or compiler behavior;
- Prime- or model-specific prompting;
- MCP session pooling, critic, scoring framework, or benchmark harness;
- change to `gh_edit`, `gh_snapshot`, flow syntax, T*/C*, or receipt correlation;
- cleanup of the two separately documented knowledge-injector baseline failures.

## End-to-end ownership invariant

Every request proceeds through these ownership stages:

```text
exact caller selector
-> proxy-owned component-type identity
-> source-kind provenance
-> temporary implementation metadata
-> existing Params projection
-> one correlated per-selector outcome
-> one batch result
-> existing public MCP result projection
```

Each stage publishes one complete fact set. A later stage may add facts but must not
overwrite or erase a previously completed authoritative stage.

In particular:

- caller strings are never rewritten inside selector evidence;
- temporary-instance names never replace proxy names;
- implementation assembly facts never masquerade as `.ghuser` package provenance;
- ranking and knowledge never select component identity;
- per-item failures never disappear from a mixed batch;
- batch success and MCP success report completion of the admitted batch, not success of
  every item.

## Current behavior being corrected

### Live catalog

`GrasshopperHandler.SearchLibrary()` currently reads the live
`GH_ComponentServer.ObjectProxies` collection but ordinary search:

- iterates registration order;
- stops once `results.Count >= limit`;
- excludes obsolete proxies but not hidden proxies explicitly;
- applies case-insensitive category substring matching across `Category` and
  `SubCategory`;
- uses case-insensitive exact `Desc.Name` equality for `exact=true`;
- otherwise uses literal substring matching over name, nickname, and description.

The installed host exposes `FindObjects()`, `CompareProxies()`, aliases, and alias
targets. The qualification established that those host facilities are the correct
ordinary retrieval owner.

### Metadata

The managed `/gh/batch-component-info` endpoint accepts GUIDs and reads proxy identity
plus SDK-backed ports. The public MCP path currently accepts names only, consults
`UnifiedStore`, and may select the first exact library result. The managed endpoint also
currently replaces proxy `Name` and `NickName` with temporary-instance values. Both
behaviors violate the ownership invariant.

### Creation and canvas identity

Component creation already refuses ambiguous exact name or nickname matches and directs
the caller to use a GUID. This slice aligns discovery and metadata with that rule. It
does not alter creation behavior or canvas identity.

## `gh_library` request branches

### Audit branch

```text
audit=true
-> execute the existing audit enumeration and filtering
-> preserve the existing audit JSON response shape
-> bypass ordinary native ranking
```

Audit counts, filters, ordering, fields, and eligibility remain unchanged. Audit results
receive no `sourceKind`, ranking metadata, provenance, or ordinary count additions.

### Catalog branch

```text
audit=false
AND search absent
-> enumerate the complete live proxy set
-> retain proxies where Obsolete == false
-> exclude proxies carrying the hidden exposure flag
-> preserve current Category/SubCategory filtering
-> order with CompareProxies
-> break remaining ties by canonical GUID ordinal
-> apply the public limit
```

Catalog components contain proxy descriptive identity plus `sourceKind`. They omit
`nativeScore` and `matchSource` because no match operation occurred.

### Search branch

```text
audit=false
AND search present
-> pass the caller's exact search string as one FindObjects term
-> use ObjectProxies.Count as maximumResults
-> require a complete proxy/score projection
-> retain proxies where Obsolete == false
-> exclude proxies carrying the hidden exposure flag
-> preserve current Category/SubCategory filtering
-> when exact=true, retain only case-insensitive exact Desc.Name matches
-> preserve every exact-name duplicate
-> order by native score descending
-> break equal scores with CompareProxies
-> break any remaining tie by canonical GUID ordinal
-> apply the public limit
```

Rook does not split, trim, stem, rewrite, or expand the caller's search string. Aliases
may influence ordinary native search because Grasshopper owns them. Alias targets never
masquerade as exact-name matches.

No rule prefers a native component over a third-party component. Native ranking proposes
candidates; the selected GUID establishes identity.

### Category compatibility

Category filtering remains:

```text
case-insensitive substring match against Category OR SubCategory
```

It occurs before the public limit in both ordinary branches.

### Ordinary eligibility

Ordinary catalog, search, and exact-name resolution use exactly:

```text
Obsolete == false
AND hidden exposure flag is absent
```

Quarantined or obscure proxies are not excluded merely for those classifications unless
they are also hidden or obsolete. Audit retains its existing broader visibility.

### Native failure behavior

Failure to obtain the component server, call `FindObjects()`, project its complete
candidate/score result, compare proxies, or compute the complete filtered set returns a
truthful tool failure. Rook does not fall back to registration-order search, repeated
over-fetching, knowledge lookup, or a copied index.

## Candidate contract

### Proxy-owned descriptive identity

Search candidates, catalog components, successful metadata outcomes, and ambiguity
candidates derive these fields only from the selected proxy:

```text
name: non-null exact host string
nickName: exact host string or actual host null
description: exact host string or actual host null
category: exact host string or actual host null
subCategory: exact host string or actual host null
guid: canonical lowercase GUID
sourceKind: compiled | user_object
```

Empty host strings remain empty strings. Missing properties, unreadable values, invalid
GUID projection, or unexpected runtime types are projection failures; they are not
coerced to strings or null.

Temporary-instance `Name` and `NickName` must not replace proxy values. Instance-owned
facts appear only under `implementation`.

### Source-kind projection

```text
proxy Kind == CompiledObject
-> sourceKind = compiled

proxy Kind == UserObject
-> sourceKind = user_object

missing, unreadable, or any other proxy Kind
-> catalog/search fails with no candidate list
-> metadata item returns projection_failure / proxy_projection_failed
```

Unknown source kind never falls back to compiled or user-object behavior.

### Search evidence

Actual search candidates add:

```text
nativeScore: exact finite JSON number from FindObjects
matchSource: native_search | exact_name
```

`matchSource=exact_name` means Rook applied case-insensitive exact `Desc.Name` equality.
It is not inferred from the score.

Ambiguity candidates come from a complete exact-name scan that does not call
`FindObjects()` and therefore use:

```text
nativeScore: null
matchSource: exact_name
```

A non-finite or unprojectable native score fails the complete search. It is never
serialized, replaced with null, or silently reordered.

### Two-level provenance disclosure

Ordinary catalog/search and ambiguity candidates expose only proxy descriptive identity,
the exact component-type GUID, and `sourceKind`. They do not expose assembly paths,
`.ghuser` paths, fingerprints, or implementation fields.

Detailed provenance is projected only for metadata GUIDs selected explicitly by the
caller. A caller resolving ambiguity may pass every candidate GUID in one
`gh_batch_component_info` request.

Search and catalog projection never instantiate candidates, construct
`GH_UserObject`, read user-object `Data`, or hash content.

## `gh_library` response contract

Successful ordinary responses retain the legacy fields:

```text
count
components
```

They add:

```text
returnedCount
totalMatches
truncated
```

Both ordinary branches compute the complete eligible filtered set. Therefore every
successful ordinary response includes all three additions and satisfies:

```text
count == returnedCount == components.length
totalMatches == complete eligible filtered-set size
truncated == returnedCount < totalMatches
```

If completeness cannot be proven, the operation fails rather than emitting guessed
counts.

Illustrative search payload using synthetic values:

```json
{
  "count": 1,
  "returnedCount": 1,
  "totalMatches": 2,
  "truncated": true,
  "components": [
    {
      "name": "Example Component",
      "nickName": "Example",
      "description": "Example proxy description.",
      "category": "Example",
      "subCategory": "Operators",
      "guid": "11111111-1111-1111-1111-111111111111",
      "sourceKind": "compiled",
      "nativeScore": 42.0,
      "matchSource": "native_search"
    }
  ]
}
```

Illustrative audit payload preserving the existing shape:

```json
{
  "totalScanned": 2,
  "deprecatedCount": 1,
  "obsoleteCount": 0,
  "hiddenCount": 1,
  "components": [
    {
      "name": "Hidden Example",
      "nickName": "Hidden",
      "category": "Example",
      "subCategory": "Legacy",
      "guid": "22222222-2222-2222-2222-222222222222",
      "obsolete": false,
      "exposure": 16,
      "exposureLabel": "hidden"
    }
  ]
}
```

Synthetic GUIDs in examples illustrate shape only and are not production fixtures or
preferred components.

## `gh_batch_component_info` request contract

The public tool accepts exactly one nonempty selector family:

```text
names: nonempty array of JSON strings
OR
guids: nonempty array of JSON strings
```

Requests containing both families, neither family, an empty selected family, a
non-array family, or a non-string element fail before target contact. The handler does
not trim, case-fold, coerce, or otherwise rewrite admitted strings.

For every admitted element, in original order and including duplicates:

```text
selector.kind: name | guid
selector.value: exact caller-supplied string
-> exactly one result item
```

For GUID selectors:

```text
invalid syntax
-> invalid_guid outcome
-> no canonical guid field

valid syntax
-> guid is canonical lowercase D-format
-> direct live proxy lookup by that GUID
```

Explicit GUID lookup is not limited by ordinary search eligibility. A caller that
already possesses a hidden or obsolete GUID may request its metadata directly. Name
lookup uses the ordinary eligible proxy set.

## Name resolution and ambiguity

Names remain supported for compatibility, but knowledge never resolves type identity.
For each name, Rook performs a complete live case-insensitive exact `Desc.Name` scan over
the ordinary eligible proxies:

```text
zero matches
-> not_found

one match
-> selected proxy GUID
-> authoritative metadata pipeline

multiple matches
-> ambiguous_name
-> every candidate in deterministic CompareProxies/GUID order
-> no candidate selection or metadata dispatch for that item
```

Ambiguity candidates use the candidate contract above. No rule prefers core or
third-party identity.

## Metadata projection phases

Selected metadata proceeds through fixed phases:

```text
selector parsing or name resolution
-> complete proxy identity projection
-> complete source-kind provenance projection
-> temporary component instantiation
-> complete implementation projection
-> existing GetComponentParams projection
```

Completed phases accumulate monotonically. Later failure retains each earlier completed
phase and omits only the incomplete phase and its successors.

### Compiled provenance

For `sourceKind=compiled`, `provenance` always contains exactly:

```text
libraryGuid: canonical lowercase non-null GUID
libraryName: exact host string or actual host null
libraryVersion: exact host string or actual host null
assemblyFullName: exact host string or actual host null
assemblyVersion: exact host string or actual host null
assemblyLocation: exact host string or actual host null
```

Empty host strings remain empty strings. `Guid.Empty` remains a non-null canonical GUID
when that is the exact host value.

Rook obtains the record from `FindAssembly(LibraryGuid)`. A not-found assembly record,
missing property, unreadable value, invalid GUID projection, or unexpected runtime type
produces:

```text
status: projection_failure
error: provenance_projection_failed
```

No runtime assembly or proxy location fallback is permitted to manufacture compiled
provenance.

### User-object provenance

For `sourceKind=user_object`, `provenance` always contains exactly:

```text
path: exact non-null host string
contentByteLength: non-negative integer | null
contentSha256: uppercase 64-character SHA-256 string | null
```

Rook uses the exact selected proxy and exact host-returned user-object path. It does not
parse the path into package, family, author, or version identity.

Installed `GH_UserObject.Data` is handled exactly:

```text
Data == null
-> contentByteLength = null
-> contentSha256 = null
-> provenance remains successful

Data is byte[]
-> contentByteLength = exact byte count
-> contentSha256 = exact uppercase SHA-256

any other runtime type
-> provenance_projection_failed
```

A missing or unreadable path, `GH_UserObject` construction failure, byte conversion
failure, or hashing failure also produces `projection_failure /
provenance_projection_failed`. Raw `Data` bytes are never retained or returned.

### Temporary implementation metadata

After complete provenance, Rook creates one temporary instance for selected metadata.
The instance is not inserted into a document and is used only for implementation and
port projection.

`implementation` always contains exactly:

```text
baseGuid:
  canonical lowercase non-null GUID for user_object
  null for compiled

componentGuid:
  canonical lowercase non-null GUID

runtimeType:
  exact non-null host string

runtimeAssemblyName:
  exact host string or actual host null

runtimeAssemblyVersion:
  exact host string or actual host null

runtimeAssemblyLocation:
  exact host string or actual host null
```

Empty host strings remain empty strings. Missing properties, unreadable values, invalid
GUID projection, or unexpected runtime types produce:

```text
status: projection_failure
error: implementation_projection_failed
```

That outcome retains selector, canonical GUID, complete proxy identity, `sourceKind`,
and complete provenance. It omits `implementation` and `params`.

`baseGuid`, `componentGuid`, runtime type, and runtime assembly describe execution
implementation only. They never identify the package that supplied a `.ghuser`.

### Params compatibility

`GetComponentParams()` remains unchanged.

```text
existing object result
-> params contains the existing inputs/outputs or simple-parameter shape

existing null result, including an internally caught exception
-> successful metadata outcome with params: null
```

This slice does not add `params_projection_failed`, refactor `GetComponentParams()`, or
reinterpret optionality, access, type names, source counts, recipient counts, or simple
parameter behavior.

## Successful metadata outcome

Unique-name selectors and GUID selectors return the same success shape. Only the
selector differs.

```text
selector
status = success
guid
proxy-owned name/nickName/description/category/subCategory
sourceKind
closed source-kind provenance
closed implementation
params using the existing projection
```

Illustrative compiled success using synthetic identity:

```json
{
  "selector": {"kind": "guid", "value": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"},
  "status": "success",
  "guid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "name": "Example Component",
  "nickName": "Example",
  "description": "Example proxy description.",
  "category": "Example",
  "subCategory": "Operators",
  "sourceKind": "compiled",
  "provenance": {
    "libraryGuid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "libraryName": "Example Library",
    "libraryVersion": "1.0.0",
    "assemblyFullName": "Example, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null",
    "assemblyVersion": "1.0.0.0",
    "assemblyLocation": "C:\\Example\\Example.gha"
  },
  "implementation": {
    "baseGuid": null,
    "componentGuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "runtimeType": "Example.Component",
    "runtimeAssemblyName": "Example",
    "runtimeAssemblyVersion": "1.0.0.0",
    "runtimeAssemblyLocation": "C:\\Example\\Example.gha"
  },
  "params": null
}
```

## Per-selector outcome contract

The closed status set is:

```text
success
invalid_guid
not_found
ambiguous_name
projection_failure
instantiation_failure
```

### Invalid GUID

```text
retain selector
omit guid and every later phase
error = invalid_guid
```

### Valid but missing GUID or missing name

```text
retain selector
retain canonical guid for a valid GUID selector
omit guid for an unresolved name selector
error = component_not_found
```

### Ambiguous name

```text
retain selector
return every complete candidate
perform no metadata projection for that selector
```

### Proxy projection failure

```text
retain selector
retain canonical guid when parsing or name resolution completed
omit incomplete proxy fields and every later phase
status = projection_failure
error = proxy_projection_failed
```

Unreadable or unsupported proxy `Kind` is a proxy projection failure.

### Provenance projection failure

```text
retain selector
retain canonical guid
retain complete proxy identity and sourceKind
omit provenance, implementation, and params
status = projection_failure
error = provenance_projection_failed
```

### Instantiation failure

```text
retain selector
retain canonical guid
retain complete proxy identity, sourceKind, and provenance
omit implementation and params
status = instantiation_failure
error = component_instantiation_failed
```

### Implementation projection failure

```text
retain selector
retain canonical guid
retain complete proxy identity, sourceKind, and provenance
omit implementation and params
status = projection_failure
error = implementation_projection_failed
```

No later failure rewrites an earlier status, substitutes knowledge, retries, or falls
back to another identity path.

## Batch result and MCP semantics

An admitted batch is complete only when it returns exactly one valid ordered outcome per
selector, including duplicates.

For every complete admitted batch:

```text
top-level internal success = true
public MCP isError = false
count == results.length
errors == number of results whose status != success
```

This remains true when every per-selector outcome is non-success. Batch success means the
admitted batch was evaluated completely; it does not mean every requested component was
found or projected.

These conditions produce top-level failure and existing public `isError=true`:

```text
invalid selector-family shape
target-wide failure
component-server failure
malformed host response
missing, extra, or reordered outcomes
unknown outcome status or invalid outcome shape
```

The existing public structured-result owner remains authoritative. This slice adds no
new MCP result wrapper, output schema, or error taxonomy outside the per-item contract.

## Names-only compatibility summaries

Names-only responses retain the legacy summaries:

```text
resolved:
  each exact caller-supplied name string whose outcome is success
  -> canonical GUID

unresolved:
  each exact original name selector whose outcome is not success
  -> original request order
  -> duplicates preserved
```

Because `resolved` is a mapping, repeated identical successful names necessarily collapse
there. The ordered `results` array is authoritative and preserves every request item.

GUID-only requests omit `resolved` and `unresolved`.

## Creation and compact execution compatibility

Short-name creation remains supported:

```text
unique component name
-> create as before

ambiguous native/plugin name
-> refuse
-> require selected component-type GUID

exact component-type GUID
-> deterministic type creation
```

The identity layers remain:

```text
component-type GUID
-> selected catalog type identity

T1, T2, ...
-> new instances inside one gh_edit batch

C1, C2, ...
-> existing instances in gh_snapshot

gh_edit receipt
-> T* to C* and physical instance GUID correlation
```

Neither `gh_edit` nor `gh_snapshot` acquires a new lookup, shorthand, provenance, or
identity layer.

## Knowledge and dispatcher corrections

`gh_library` and `gh_batch_component_info` are authoritative live discovery tools.
`KnowledgeInjector` must skip both tools. It must not add canvas-size, mesh-validity,
recipe, workflow, or other learned hints to their results.

This does not remove knowledge as future advisory context. Later retrieval may propose
semantic candidates, but it may not alter native ranking, component GUIDs, provenance,
port metadata, or ambiguity decisions.

The direct ChatRunner `ToolDispatcher` transformation must preserve the exact boolean
`gh_library.exact` argument. Canonical MCP dispatch already owns the remaining public
validation and targeting behavior.

These contracts apply through:

- direct public MCP calls;
- contained targets invoked through `rook_tools_call`;
- direct ChatRunner tools already supported by `ToolDispatcher`.

No second capability catalog or dispatch table is introduced.

## Frozen Opus control

The unchanged-surface control is pinned to:

```text
C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-opus-control
```

Reviewed row path:

```text
C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-opus-control/operator/row.json
```

Model custody:

```text
model: anthropic/claude-opus-4-6
provider: anthropic
modelId: claude-opus-4-6
api: anthropic-messages
base URL containing no embedded credentials: https://api.anthropic.com
intent: Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.
```

Static capability custody:

```text
source artifact: C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v7
skill SHA-256: 0F7C8D1F2D612FFB7522469C4E3D467985E8872585CA3C18DF9B46BD1A84D36E
checkpoint SHA-256: 76A7C0CFF04DEF83A75519A546AC812804AC32BBF30CC14609A6D52950248964
rook_full adapter SHA-256: E7577F0EC8A9B504712BC73290BB8F4C673E9677AEF952CFBFC346F206A62996
```

The isolated row and model configuration must pin the exact generation settings and the
credential environment-variable names used by the Anthropic provider. No credential
value enters an artifact.

The skill body, checkpoint, adapter transport, `search/read/call` surface, intent, full
Rook profile, evidence rules, and final-inspection request remain unchanged from the
reviewed V7 method. Only provider/model configuration, model-custody checks, sibling
paths, and a fresh reviewed Rhino target differ.

Evidence contract:

```text
one natural Prime termination
zero operator reruns
zero adapter retries
no cleanup
Prime JSONL retained exactly
one native Prime session retained exactly
stderr retained exactly
one independent final gh_snapshot after normal termination and intact targeting/evidence
request and result retained in final-inspection.jsonl
missing/corrupt evidence, cancellation, forced termination, or target drift -> no inspection
```

The control records semantic plan, discovery queries, candidate ranks, irrelevant
results consumed, whether `Series` is discovered, schema reads, invalid calls, time and
tokens before mutation, edits, snapshots, corrections, mechanical outcome, and semantic
fidelity. Success demonstrates compensation ability only.

## Verification requirements

### Managed discovery tests

Use synthetic causal proxies, never installed-plugin fixtures, to prove:

- audit bypasses ordinary ranking and preserves its exact response shape;
- catalog browsing uses complete enumeration, ordinary eligibility, category filtering,
  `CompareProxies`, GUID ties, and limit-after-ordering;
- search calls `FindObjects()` once with the caller string and live proxy count;
- exact/category filtering precedes limiting;
- native score ordering, equal-score comparison, and GUID ties are deterministic;
- non-finite or unprojectable scores fail the search;
- aliases can influence ordinary search but not exact-name equality;
- hidden and obsolete eligibility is exact;
- third-party candidates are not filtered by a core allowlist;
- unknown proxy Kind fails rather than being reclassified;
- search/catalog never instantiate, construct user objects, read `Data`, or hash content;
- count equations are exact.

### Managed metadata tests

Prove:

- input admits exactly one nonempty selector family;
- selector strings, order, case, and duplicates are preserved;
- parsed and resolved GUIDs use canonical lowercase format;
- proxy fields remain authoritative when instance names differ;
- name lookup uses complete eligible exact-name matching;
- ambiguity preserves every candidate and dispatches no metadata for that item;
- GUID lookup bypasses `UnifiedStore` and ordinary eligibility;
- compiled provenance uses `FindAssembly(LibraryGuid)` with the exact closed shape;
- missing compiled assembly provenance fails locally without fallback;
- user-object provenance returns exact path and paired content fields;
- null `Data` succeeds with paired nulls;
- user-object construction, type, conversion, and hashing failures become provenance
  projection failures;
- implementation fields, nullability, and source-kind-specific `baseGuid` are exact;
- implementation failure retains provenance and omits implementation/params;
- temporary-instance names never overwrite proxy identity;
- `GetComponentParams()` remains unchanged and null remains a successful `params:null`;
- every failure prefix retains all earlier completed phases;
- mixed batches continue item by item;
- one ordered outcome exists per selector;
- count/error equations and all-failure batch success are exact;
- names-only `resolved`/`unresolved` summaries remain compatible;
- GUID-only results omit those summaries;
- malformed host correlation becomes top-level failure;
- ambiguous name creation remains refused.

### Python boundary tests

Prove through direct MCP and `rook_tools_call` paths:

- `gh_library` schemas, arguments, additive results, and failures pass through the
  existing public projection;
- `gh_batch_component_info` selector validation and ordered outcomes are identical;
- complete admitted all-failure batches remain MCP `isError=false`;
- top-level request/target/host failures become MCP `isError=true`;
- no gateway double wrapping appears;
- both authoritative tools bypass knowledge injection;
- direct `ToolDispatcher` preserves `exact`;
- the two unrelated knowledge-injector baseline failures retain their exact identities
  and signatures, with no new failures.

## Production module boundary

Production changes are limited to:

```text
src/Rook/Handlers/GrasshopperHandler.cs
mcp_server/src/rook/server.py
mcp_server/src/rook/agent/tool_dispatcher.py
mcp_server/src/rook/learning/knowledge_injector.py
```

`NativeGhBridgeRegistrar` already forwards library arguments and the metadata request
body unchanged; it does not require modification. Focused managed and Python test files
may be added.

No new production module, registry, search service, cache, result framework, persistent
catalog, identity abstraction, or endpoint is permitted. If another production owner
becomes materially necessary, stop for scope review.

## Claims

After implementation and review, this slice may claim:

- ordinary component search uses Grasshopper's native ranked catalog and aliases;
- Rook preserves category and exact-name semantics while filtering before limiting;
- ordinary search excludes hidden and obsolete candidates;
- native and installed third-party candidates remain discoverable without an allowlist;
- duplicate component names cannot silently select the wrong implementation;
- caller selectors and per-item outcomes remain correlated in order;
- selected GUIDs flow directly into authoritative metadata;
- proxy identity, source-kind provenance, implementation, and Params have separate
  owners;
- compiled and user-object provenance are truthful source-specific variants;
- agents retain compact T*/C* identities for graph execution;
- unrelated knowledge hints no longer modify authoritative discovery results.

It may not claim:

- fuzzy, semantic, intent-aware, or typo-tolerant retrieval;
- stable native-score values across Grasshopper versions;
- visibility of plugins that failed to load or register;
- portable `.ghuser` proxy GUIDs;
- `.ghuser` package, author, family, or package-version identity;
- that runtime assembly identifies the supplier of a `.ghuser`;
- runtime semantic correctness from metadata alone;
- improved model reasoning independently of controlled comparison;
- knowledge or DSPy effectiveness.

## Anti-quagmire stop conditions

Stop before implementation expansion if:

- native search requires a persistent or parallel catalog;
- category completeness requires speculative repeated over-fetching;
- search would instantiate candidates or hash user-object content;
- provenance requires archive parsing or inferred package labels;
- embeddings, fuzzy matching, custom aliases, or knowledge migration enter scope;
- a new GUID or short-ID family is proposed;
- `gh_edit`, `gh_snapshot`, T*/C*, flows, or receipts must change;
- more than the four existing production owners need material changes;
- a model result is used to add witness-specific ranking or prompts.

The KISS boundary is:

> One native retrieval owner, one proxy-owned component-type GUID, one source-specific
> provenance handoff, one existing metadata owner, existing compact graph identities,
> and truthful correlated outcomes.
