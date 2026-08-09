# Grasshopper Native Component Discovery Qualification

**Status:** Task 0 evidence captured; production policy remains review-gated

**Repository baseline:** `4bf6fad8418d90590f3ecb4e7cc7921d7894deae`

**Approved design dependency:** `d840f70d3aa40ab77374ef72cd6e152557c4effa`

**Successful capture lane:** `rook-gh-native-discovery-task0-v2`

## Baseline and custody

The successful capture ran once against Rhino process `38672`, native port `55902`, and
Rhino document serial `268435457`. The installed host reported Rhino and Grasshopper
version `8.34.26215.11001`. The live Grasshopper catalog contained `1,890` proxies.

The first lane remains separately retained as a failed Python.NET invocation-contract
observation. Its HTTP `400` response proves only that the original two-argument binding
was wrong. The V2 lane supplied typed placeholders for both out arrays and produced the
accepted live `(count, proxies, weights)` projection.

The successful request returned HTTP `200`, internal `success=true`, zero created Rhino
objects, and an empty stderr stream. Grasshopper canvas object counts were `0` before and
`0` after. No model, component instantiation, canvas edit, retry, or second host request
occurred.

## Exact call budget and non-mutation evidence

| Operation | Count | Evidence |
|---|---:|---|
| Native `/execute` requests | 1 | retained invocation response |
| `FindObjects` | 21 | seven fixed queries, three runs each |
| `FindObjectByName` | 7 | once per fixed query |
| `AliasTargets` | 7 | once per fixed query |
| cached `FindAssembly` | 564 | one per distinct observed `LibraryGuid` |
| `FindAssemblyByObject` | 115 | bounded selected metadata specimens |
| `CreateInstance` | 0 | probe budget and static exclusion |
| `EmitObject` | 0 | probe budget and static exclusion |
| Rhino objects created | 0 | native invocation receipt |
| Grasshopper canvas delta | 0 | `0 -> 0` |

`CompareProxies` supplied host ordering for catalog and equal-score ties. The artifact
records zero comparison errors but does not claim an exact comparator invocation count.

## Host and catalog inventory

The complete catalog contained:

```text
1,890 total proxies
1,334 proxies with affirmative core assembly provenance
7 proxies with affirmative third-party assembly provenance
549 proxies whose LibraryGuid had no FindAssembly result
320 hidden proxies
```

Every one of the 549 unresolved proxies was a `.ghuser` user object. Their installed
families, derived only from the retained host paths, were:

| Installed user-object family | Proxy count |
|---|---:|
| `honeybee_grasshopper_energy` | 139 |
| `ladybug_grasshopper` | 122 |
| `dragonfly_grasshopper` | 109 |
| `honeybee_grasshopper_radiance` | 89 |
| `honeybee_grasshopper_core` | 70 |
| `fairyfly_grasshopper` | 20 |

This proves that installed user-object plugins remain present and searchable. It does not
establish a uniform plugin-provenance contract for them.

## Fixed-query latency and ordering

| Query | Native candidates | Run 1 ms | Run 2 ms | Run 3 ms | Native rank 1 |
|---|---:|---:|---:|---:|---|
| `Series` | 261 | 6.970 | 3.485 | 2.511 | Series |
| `Range` | 228 | 15.389 | 6.396 | 3.485 | Range |
| `Multiplication` | 18 | 4.014 | 5.319 | 5.978 | Multiplication |
| `Addition` | 91 | 4.326 | 4.002 | 3.836 | Addition |
| `Construct Point` | 58 | 6.360 | 9.043 | 6.837 | Construct Point |
| `Add` | 112 | 2.857 | 2.289 | 2.073 | Addition |
| `Point` | 371 | 3.063 | 3.261 | 3.628 | Point |

All 21 calls completed below 16 ms. Ordered GUIDs and native weights were identical across
all three runs for every query. Exact canonical components ranked first, and ordinary
`Add` ranked the core Addition component first. Native scores are retained only as
host-version-specific diagnostic observations; ordering is the relevant behavior.

## Complete legacy predicate versus native candidates

Every property required by the complete legacy predicate was read successfully, so
`legacy_comparisons_complete=true` is supported. Native search returned broader candidate
sets than the literal legacy predicate for every fixed query.

| Query | Complete legacy matches | Native candidates | Legacy-only matches |
|---|---:|---:|---:|
| `Series` | 15 | 261 | 2 |
| `Range` | 18 | 228 | 0 |
| `Multiplication` | 3 | 18 | 1 |
| `Addition` | 11 | 91 | 2 |
| `Construct Point` | 1 | 58 | 0 |
| `Add` | 33 | 112 | 2 |
| `Point` | 193 | 371 | 6 |

## Eligibility deltas

Every fixed-query legacy-only omission was a non-obsolete hidden core proxy. There were
no unexplained or third-party legacy-only omissions.

| GUID | Name | Category | Affected queries |
|---|---|---|---|
| `2844fec5-142d-4381-bd5d-4cbcef6d6fed` | Sketch | Params | Series |
| `586706a8-109b-43ec-b581-743e920c951a` | Series Addition | Maths | Series, Addition, Add |
| `63fff845-7c61-4dfb-ba12-44d481b4bf0f` | Multiply | Vector | Multiplication |
| `fb012ef9-4734-4049-84a0-b92b85bb09da` | Addition | Vector | Addition, Add |
| `1f18e802-4ab9-444f-bf3c-3e7e421a2acf` | Point List | Display | Point |
| `3edc4fbd-24c6-43de-aaa8-5bdf0704373d` | Swing Arc | Curve | Point |
| `769f9064-17f5-4c4a-921f-c3a0ee05ba3a` | Catenary Ex | Curve | Point |
| `bc26bf46-e81b-429a-b168-16d50cc89bd7` | Coordinate Mask | Vector | Point |
| `c6fe61e7-25e2-4333-9172-f4e2a123fcfe` | Offset Loose 3D | Curve | Point |
| `fa20fe95-5775-417b-92ff-b77c13cbf40c` | Mesh Point | Params | Point |

Recommended ordinary eligibility is `not obsolete AND exposure != hidden`, matching the
observed native-search boundary. Apply that same policy to ordinary catalog browsing for
coherence. Preserve the existing `audit=true` branch unchanged, including its broader
audit-specific behavior and JSON response shape. This is a review recommendation, not an
implemented decision.

## Category-filter completeness

For query `Series`, the first `Kangaroo2` candidate appeared at native rank `51`, beyond
the current public limit of 50. The complete native candidate set contained 20 such
candidates. This directly establishes that category filtering must occur before the
public limit. It does not justify repeated speculative over-fetching because full native
candidate retention was already ordinary in this installed catalog.

The public category predicate should remain its existing case-insensitive substring match
against `Category OR SubCategory`.

## Exact-name duplicates

The complete non-obsolete catalog contained 53 exact-name duplicate groups. At least 33
groups retained two or more non-hidden candidates, so ambiguity is not merely a hidden
legacy artifact.

`Addition` itself needs narrower wording: its two exact catalog candidates are the
exposed primary Maths component `a0d62394-a118-422d-abb3-6af115c75b25` and the hidden
Vector component `fb012ef9-4734-4049-84a0-b92b85bb09da`. Native search returned only the
exposed component. Other groups still contain multiple non-hidden candidates.

`FindObjectByName` returned only one candidate and therefore cannot own public exact-name
identity. Recommended identity behavior remains a complete eligible-proxy exact-name
scan: zero matches is not found, one is selected, and multiple is an explicit ambiguity
containing every candidate. No rule should prefer core or third-party identity.

## Third-party visibility

Third-party components appeared directly in native ranked results. Examples include
Ladybug Color Range at rank 3 for `Range` and Honeybee Add components near the top of
`Add`. This establishes installed third-party discoverability without a curated allowlist.

Two compiled third-party assemblies had affirmative `FindAssembly` provenance:

| Assembly | CLR assembly version | Host library version | Example component |
|---|---|---|---|
| GhPython | `8.34.26215.11001` | empty | Marshalling signal parameter |
| Ladybug.Grasshopper | `0.0.0.1` | empty | LB Image Viewer |

The two specimens are environmental evidence only, not durable product fixtures.

## Host provenance inventory

The 564 cached `FindAssembly` lookups produced 15 found libraries and 549 not-found user
object libraries. The found set comprised 13 core libraries and two affirmative
third-party libraries. All 115 selected `FindAssemblyByObject` observations succeeded,
but none covered the 549 `.ghuser` proxies.

Compiled proxies expose useful host facts such as `LibraryGuid`, assembly/library name,
assembly full name, assembly version, and location. Those observations are sufficient to
describe compiled candidates but are not a complete cross-surface production contract.
For `.ghuser` proxies, `FindAssembly(LibraryGuid)` returned not found; raw host paths
identify installed families observationally, but path parsing is not an approved plugin
identity system.

Therefore Task 0 cannot truthfully select the final exact provenance field set required
by the identity-handoff invariant. A candidate compiled-only field set would include
canonical lowercase `libraryGuid`, exact nullable `libraryName`, exact nullable
`libraryVersion`, exact nullable `assemblyFullName`, and exact nullable `assemblyVersion`.
It must not be promoted until a tiny metadata-only qualification establishes what the
same fields mean for retained `.ghuser` GUIDs. Absolute source paths should remain
evidence, not automatically become model-facing identity fields.

## Candidate identity handoff assessment

The evidence supports the ownership chain:

```text
native ranked search proposes complete candidates
-> eligible exact-name scan preserves ambiguity
-> selected component-type GUID establishes identity
-> authoritative metadata validates the selected type
-> existing T* and C* shorthand owns transaction and canvas identity
```

Search ranking and knowledge must not select identity. Full GUIDs are needed only at the
component-type handoff; existing `T*` and `C*` identities remain unchanged for graph
editing and snapshots.

## Recommended post-Task 0 decisions

Keep these four decisions independent:

1. **Search adoption — adopt native `FindObjects`.** Use the full proxy count, preserve
   the caller's search string, apply compatibility filters before limiting, and retain
   deterministic native-score/`CompareProxies`/GUID ordering.
2. **Ordinary eligibility — exclude obsolete and hidden proxies.** Preserve the existing
   audit branch separately. All measured compatibility losses were hidden core proxies.
3. **Identity ambiguity — refuse rather than collapse.** Resolve names through a complete
   eligible exact-name scan, return all ambiguous candidates, and require a selected GUID.
4. **Provenance — remain blocked.** Compiled provenance is usable, but 549 installed
   `.ghuser` proxies lack a qualified metadata-side provenance handoff.

The first three recommendations may be pinned in the specification after independent
review. Production planning remains blocked until the fourth is either qualified or the
identity invariant is deliberately narrowed by reviewed design.

## Explicit unresolved or blocked findings

- A uniform provenance contract across compiled and `.ghuser` components is unproven.
- No metadata-side specimen was captured for Ladybug, Honeybee, Dragonfly, or Fairyfly
  `.ghuser` components.
- If metadata parity is required, the next evidence slice should call only the existing
  metadata owner for a few already-retained `.ghuser` GUIDs. It must not repeat search.
- `CompareProxies` call count was not instrumented; only its zero-error outcome and
  resulting deterministic ordering are retained.

## Non-claims

This qualification does not prove:

- cross-version score stability or performance;
- fuzzy, semantic, or intent-aware retrieval;
- that every installed plugin always registers successfully;
- a complete user-object provenance contract;
- model selection quality or semantic fidelity;
- production behavior, because no production code changed;
- that the audit response should change;
- runtime correctness of a component merely because its metadata is discoverable.

## Raw evidence paths and SHA-256

Successful V2 evidence:

| Artifact | SHA-256 |
|---|---|
| `native-discovery.json` | `254A9BF5A8EEE5DCCA72A37AD08DF20EDF63271F55E2F14AC4587BC180481988` |
| `invoke-result.json` | `2091AD9243ECA3B8BD934A8730A79304E1FC488151ED5358D7F3C162ED4B8E5F` |
| `stderr.txt` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `target.json` | `63CE846465A22E03BD1DE9BCB074B3FA9E5A34FCA68BA5A2F619718EBBFE392A` |

The raw files remain outside Git under
`C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0-v2`. The consumed V1
lane and its response hash
`8351F36888FF20E04ACA0EE3E83D6E3C1626D255AF8B9200C24F1DA7390EAAB1`
remain preserved separately.
