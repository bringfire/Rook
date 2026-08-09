# Grasshopper User-Object Provenance Qualification Design

**Status:** Design complete; awaiting independent review before `writing-plans`
**Date:** 2026-08-09
**Amended:** 2026-08-09
**Baseline:** `a867f8e06ae8aca904102104c47780d02d5640b8`
**Branch:** `codex/grasshopper-user-object-provenance-qualification-design`

## Purpose

Task 0 qualified Grasshopper's native component search but left one production
prerequisite unresolved: 549 installed `.ghuser` proxies had no
`FindAssembly(LibraryGuid)` result. This slice performs one metadata-only qualification
over six exact user-object GUIDs already retained by Task 0.

It asks which host-owned identity and assembly facts are available. It does not repeat
search, parse user-object archives, infer packages from paths, or change production.

The authoritative source artifact is:

```text
C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0-v2/native-discovery.json
SHA-256: 254A9BF5A8EEE5DCCA72A37AD08DF20EDF63271F55E2F14AC4587BC180481988
```

## Identity boundaries

```text
proxy identity        = current-installation path-derived proxy GUID
user-object identity  = GH_UserObject Path + BaseGuid + Description
instantiated identity = runtime component type + resolved base assembly evidence
```

A user-object proxy GUID is a hash of its file path. It is authoritative for the
current installation, not claimed portable across machines. `BaseGuid` identifies the
base document-object type; it is not package, author, family, or version identity.

The probe enforces only:

```text
selector GUID == proxy GUID
proxy Kind == UserObject
normalized retained path == normalized proxy Location
normalized proxy Location == normalized GH_UserObject Path
```

`BaseGuid` and the temporary instance's `ComponentGuid` are recorded independently.
Their relationship is evidence, not an asserted equation.

## Frozen path-derived specimen groups

| Evidence-only label | Proxy GUID | Retained host path |
|---|---|---|
| `ladybug_grasshopper` | `003934c7-7c91-40c3-a35d-8b672e32bf7a` | `C:\Users\bring\AppData\Roaming\Grasshopper\UserObjects\ladybug_grasshopper\user_objects\LB Legend Parameters.ghuser` |
| `honeybee_grasshopper_core` | `01a59900-f860-4d3b-a2a4-629a7b867a94` | `C:\Users\bring\AppData\Roaming\Grasshopper\UserObjects\honeybee_grasshopper_core\user_objects\HB Door.ghuser` |
| `honeybee_grasshopper_energy` | `049a829b-2181-4062-b757-5f30ff7dbf18` | `C:\Users\bring\AppData\Roaming\Grasshopper\UserObjects\honeybee_grasshopper_energy\user_objects\HB Apply Room Schedules.ghuser` |
| `honeybee_grasshopper_radiance` | `003e5f4f-95ae-42ad-8178-189d51fb0433` | `C:\Users\bring\AppData\Roaming\Grasshopper\UserObjects\honeybee_grasshopper_radiance\user_objects\HB Ambient Resolution.ghuser` |
| `dragonfly_grasshopper` | `00653abd-3197-4917-b751-60698f37381a` | `C:\Users\bring\AppData\Roaming\Grasshopper\UserObjects\dragonfly_grasshopper\user_objects\DF Apply Facade Parameters.ghuser` |
| `fairyfly_grasshopper` | `06348dc2-a44c-42f4-a5d5-870fc56cfb27` | `C:\Users\bring\AppData\Roaming\Grasshopper\UserObjects\fairyfly_grasshopper\user_objects\FF Model.ghuser` |

These labels and paths describe this installed host only. They are neither package
identities nor production fixtures.

## Single-request execution

One frozen `/execute` request runs against one panel-locked Rhino process and document.
For each selector, in order, it:

1. Calls `GH_ComponentServer.EmitObjectProxy(Guid)`.
2. Checks the four identity equations.
3. Constructs `GH_UserObject` from the exact proxy `Location`.
4. Projects the user-object fields defined below.
5. Calls `FindAssemblyByObject(proxy Guid)`.
6. Calls the exact returned proxy's `CreateInstance()` once.
7. Projects the temporary instance fields defined below.
8. Calls `FindAssemblyByObject(temporary instance)`.
9. Drops references without inserting the temporary object into a document.

It must not use `CreateComponentFromGuid()`, `EmitObject()`, name fallback,
`FindObjects()`, `ObjectProxies` scanning, or any Rook product endpoint. There is no
generic `IGH_DocumentObject` disposal call.

The Grasshopper document's object count is read before the first specimen and after the
last. Equality is required for a complete probe.

### Closed budget

```text
1 /execute
6 EmitObjectProxy(Guid)
6 GH_UserObject(path) constructions/deserializations
6 proxy.CreateInstance()
6 FindAssemblyByObject(Guid)
6 FindAssemblyByObject(instance)
2 canvas object-count reads
0 search/proxy scans
0 insertion/solution/model calls
0 retries/cleanup mutations
```

Observed counts are retained. Any disagreement makes the probe incomplete.

## Path handling

The exact returned .NET string is retained unchanged as the JSON string value and is
strictly UTF-8 encoded with the artifact. Byte identity applies only to those encoded
artifact bytes. Comparison uses a separate value produced by
`System.IO.Path.GetFullPath`, Windows separator canonicalization, and ordinal
case-insensitive equality. No symlink, package, family, or version meaning is inferred.

## Compact evidence artifact

The probe writes one create-new JSON artifact. Its exact top-level keys are:

```text
schema = rook.qualification.gh_user_object_provenance.v1
capturedAtUtc
repository
sourceEvidence
target
canvas
budget
specimens
probeComplete
```

The closed supporting blocks are:

| Block | Exact keys |
|---|---|
| `repository` | `headSha`, `branch`, `worktreeStatus` |
| `sourceEvidence` | `path`, `sha256`, `schema` |
| `target` | `processId`, `port`, `documentSerialNumber` |
| `canvas` | `objectCountBefore`, `objectCountAfter`, `unchanged` |
| `budget` | `executeRequests`, `emitObjectProxyCalls`, `userObjectConstructions`, `createInstanceCalls`, `findAssemblyByProxyGuidCalls`, `findAssemblyByInstanceCalls`, `canvasObjectCountReads`, `searchCalls`, `canvasInsertions`, `solutionRequests`, `retries`, `cleanupMutations`, `modelCalls` |

`specimens` contains exactly six ordered entries. Each has exactly:

```text
selector
proxy
userObject
proxyGuidAssembly
temporaryInstance
instanceAssembly
complete
```

### Shared closed projections

`selector` has exactly:

```text
groupLabel, guid, retainedPath, normalizedRetainedPath
```

`groupLabel` is evidence-only.

Every `description` block has exactly:

```text
name, nickName, description, category, subCategory, keywords, propertyErrors
```

The first five values are exact strings or null. `keywords` is an exact ordered string
array or null. `propertyErrors` is an ordered array whose entries have exactly:

```text
property, exceptionType, message
```

A stage `error` is null or has exactly:

```text
stage, exceptionType, message
```

Identity contradictions use `exceptionType = null`. Icons, bitmaps, reflection objects,
dynamic property bags, and arbitrary serialization are prohibited.

### Proxy

`proxy` has exactly:

```text
status, guid, kind, libraryGuid, location, normalizedLocation,
obsolete, SDKCompliant, exposure, exposureName,
description, propertyErrors, error
```

`status` is `found`, `not_found`, or `error`. The installed spelling
`SDKCompliant` is preserved.

### User object and Data

`userObject` has exactly:

```text
status, path, normalizedPath, baseGuid, description, data, propertyErrors, error
```

`status` is `constructed`, `error`, or `not_attempted`.

`data` has exactly:

```text
status, runtimeType, byteLength, sha256
```

Its complete rules are:

```text
null
-> status=null; remaining values null; complete observation

System.Byte[]
-> status=bytes; runtimeType=System.Byte[]
-> exact byteLength and SHA-256
-> raw bytes never enter evidence

any other runtime type
-> status=unexpected_type; retain only exact runtime type name
-> byteLength and sha256 null; specimen incomplete

parent not attempted
-> status=not_observed; remaining values null; specimen incomplete
```

Unexpected values are never converted, enumerated, serialized, decoded, or parsed.

### Assembly observations

`proxyGuidAssembly` and `instanceAssembly` each have exactly:

```text
status,
id, name, version, authorName, authorContact, description,
assemblyName, assemblyVersion, assemblyDescription, isCoreLibrary,
location, loadingMechanism,
runtimeAssemblyName, runtimeAssemblyFullName,
runtimeAssemblyVersion, runtimeAssemblyLocation,
propertyErrors, error
```

`status` is `found`, `not_found`, `error`, or `not_attempted`. `not_found` is complete
evidence. Remaining fields are strings, booleans, or null. Neither the
`GH_AssemblyInfo` nor its `Assembly` object is serialized.

`authorName`, `authorContact`, and `description` project the exact nullable public
`GH_AssemblyInfo` scalar properties. `assemblyDescription` projects only the exact
nullable string from the runtime assembly's
`System.Reflection.AssemblyDescriptionAttribute.Description`. No other custom
attribute, attribute object, or reflection object is retained.

### Temporary instance

`temporaryInstance` has exactly:

```text
status, componentGuid, runtimeTypeFullName,
runtimeAssemblyName, runtimeAssemblyFullName,
runtimeAssemblyVersion, runtimeAssemblyLocation,
description, propertyErrors, error
```

`status` is `created`, `not_created`, `error`, or `not_attempted`. Runtime `Type` and
`Assembly` objects are never serialized.

Downstream blocks remain present with `not_attempted` status after a prerequisite
failure. Their scalar fields are null and their closed projections are empty; no
observation is fabricated.

## Completeness

A specimen is complete only when:

```text
exact proxy resolved
AND all four identity equations hold
AND required properties returned observed values or observed nulls
AND Data is null or System.Byte[]
AND FindAssemblyByObject(proxy GUID) returned found or not_found
AND proxy.CreateInstance() returned an instance
AND the temporary-instance projection completed
AND FindAssemblyByObject(instance) returned found or not_found
```

Per-specimen failures are retained and later specimens continue. Any incomplete
specimen forces `probeComplete=false`.

`probeComplete` is computed solely from host observations:

```text
all six specimens complete
AND observed counts match the closed budget
AND canvas objectCountBefore == objectCountAfter
```

It is placed into the in-memory payload before encoding. It makes no claim about the
subsequent artifact write.

The capture sequence is exact:

```text
compute probeComplete from host observations, budget, and canvas equality
-> strictly UTF-8 encode the compact artifact
-> compute SHA-256 over those exact encoded bytes
-> create-new full write
-> flush and fsync
-> print exactly: ROOK_GHUSER_PROVENANCE_OK <UPPERCASE_SHA256>\n
-> retain the outer response in invoke-result.json
-> operator verifies the exact sentinel, hash, and Rook response envelope
```

A short write, serialization failure, flush/fsync failure, or any other artifact-write
failure prints no success sentinel.

`probeComplete` cannot claim custody of the later HTTP envelope. Overall qualification
completeness is derived only during evidence review:

```text
probeComplete == true
AND invoke-result.json was written and flushed
AND HTTP status == 200
AND the exact retained response envelope has success == true
AND data.output is exactly the success sentinel plus its one trailing newline
AND data.stderr is exactly empty
AND the sentinel SHA-256 equals the independently computed compact-artifact SHA-256
```

A complete result may truthfully establish that package, author, family, or version
identity is unavailable.

## Transport custody

The compact artifact is not self-authenticating. The operator separately retains the
exact outer response using Task 0's shape:

```json
{"status_code": 200, "body": "<exact response body>"}
```

The frozen target, manifest, launcher stderr, probe source, and inert tests are also
retained. Existing one-shot refusal and create-new evidence rules are reused. No
recorder, archive, or system of record is introduced.

Fatal request failures are limited to target/listener contradiction, unavailable
component server/document, inability to read either canvas count, and compact-artifact
serialization/write failure. Specimen-local failures continue without retry, alternate
lookup, fallback, cleanup, or a second host call.

## Deterministic no-contact tests

Before authorization, inert tests prove:

- the prior artifact hash and six ordered GUID/path pairs are exact;
- only `EmitObjectProxy(Guid)` resolves proxies;
- the exact proxy receives one `CreateInstance()` call;
- both `FindAssemblyByObject` forms are recorded independently;
- `CreateComponentFromGuid`, `EmitObject`, search, scans, insertion, and solution paths
  are unreachable;
- every projection contains only its enumerated keys;
- assembly author/contact/description and runtime assembly-description scalars are
  retained exactly without retaining attribute or assembly objects;
- original paths survive while normalized Windows paths own equality;
- GUID, kind, or path contradictions make a specimen incomplete;
- null, `byte[]`, unexpected-type, and not-observed `Data` paths are causal;
- raw `Data` bytes never reach serialization;
- found, not-found, property-error, and construction-error cases are causal;
- one specimen failure does not prevent the other five;
- incomplete specimens, canvas mismatch, or budget mismatch prevent completion;
- compact and outer evidence remain separate;
- `probeComplete` depends only on host observations, budget, and canvas equality;
- full write plus flush/fsync precedes the exact success sentinel;
- write failures produce no success sentinel;
- outer HTTP status, Rook envelope, sentinel, and independently computed artifact hash
  must correlate exactly;
- manifest/evidence refusal happens before host contact.

No test contacts Rhino, Grasshopper, MCP, a model, or a provider.

## Claims and non-claims

A complete capture may establish which host-owned proxy, user-object, instance, and
assembly scalars exist; whether they support a truthful compiled/user-object
provenance contract; whether richer provenance is unavailable; and whether the canvas
count remained unchanged.

It does not establish portable path-derived identity, package/author/family/version
identity from paths, `BaseGuid` uniqueness, equality between `BaseGuid` and
`ComponentGuid`, runtime correctness, endpoint behavior, cross-machine repeatability,
or safety isolation beyond the supervised call.

> This probe qualifies the host metadata available for a future endpoint
> implementation. It does not prove that the current `/gh/batch-component-info`
> response exposes that provenance.

## Anti-quagmire stop

Stop if this requires archive parsing, path-based package inference, another host
request, product changes, a provenance registry/catalog/cache, canvas mutation, retry,
cleanup, or broader discovery qualification.

## Next sequence

After independent specification approval:

1. Invoke `writing-plans` for this qualification only.
2. Build a fresh disposable lane with inert causal tests.
3. Stop for pre-contact review.
4. Freeze a fresh target and request one explicit authorization.
5. Perform one `/execute` capture.
6. Review the evidence without further host contact.
7. Amend the discovery specification only if the identity handoff closes.
8. Write production plans only after that amendment is approved.
