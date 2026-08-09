# Grasshopper Component Discovery Coherence Design

**Status:** Task 0 design proposed for independent review; production contract provisional
**Date:** 2026-08-08
**Amended:** 2026-08-09
**Baseline:** `4bf6fad8418d90590f3ecb4e7cc7921d7894deae`
**Branch:** `codex/grasshopper-component-discovery-coherence-design`

## Purpose

Rook already exposes Grasshopper's live registered component catalog and SDK-backed
component metadata. The missing quality is a coherent ownership chain between search,
type identity, metadata lookup, and creation.

This slice establishes that chain:

```text
Grasshopper native search
-> authoritative component-type GUID
-> authoritative SDK metadata
-> agent decision
-> validated mutation
```

It does not create a new catalog, retrieval framework, or component vocabulary.
Grasshopper remains the authority for installed component registration, native search,
aliases, and native relevance scores. Rook owns filtering, public compatibility,
deterministic tie-breaking, and safe identity handoff. Knowledge owns none of those
facts.

## Identity handoff invariant

Discovery is not complete merely because it returns ranked candidates. Every public
surface that accepts or returns component-type identity must preserve a complete,
correlated, provenance-bearing handoff.

For every caller-supplied name or GUID metadata selector, in original order and
including duplicates:

```text
selector
-> exactly one outcome

selected outcome:
  original selector
  component-type GUID
  exact Task 0-qualified host provenance
  authoritative SDK metadata

ambiguous outcome:
  original selector
  every exact candidate
  the same GUID/provenance identity fields for every candidate
  no selection or metadata dispatch for that item

not-found outcome:
  original selector
  explicit bounded reason
```

Mixed batches preserve this equation item by item. An ambiguous or missing selector does
not prevent other uniquely resolved selectors in the same request from reaching the
authoritative metadata owner.

The same exact Task 0-qualified provenance field set must appear on:

- every `gh_library` catalog/search candidate;
- every successful GUID metadata outcome;
- every uniquely resolved name metadata outcome;
- every candidate inside an ambiguous-name outcome.

Task 0 must determine the exact host-owned fields, canonical representation, and
nullability. No production plan or implementation may substitute an open-ended “when
available” contract.

The layered identity model is:

```text
search ranking proposes candidates
-> provenance-bearing identity handoff distinguishes candidates
-> selected GUID obtains authoritative metadata
-> existing T* and C* identities handle graph execution
```

Ranking and knowledge never select identity.

## Motivation

The Prime Agent V4 qualification proved that a local model could use Rook's canonical
gateway in a disciplined way and create a mechanically valid Grasshopper definition.
It also exposed avoidable discovery burden:

- ordinary `gh_library` search returns registration-order matches and applies `limit`
  before completing its scan;
- broad lexical matches place plugin descriptions ahead of the intended core component;
- names, GUIDs, and metadata do not compose cleanly across `gh_library` and
  `gh_batch_component_info`;
- the direct ChatRunner transformation drops `gh_library.exact`;
- unrelated knowledge hints are injected into authoritative catalog and metadata results;
- duplicate native and third-party component names can be resolved by unsafe first-match
  behavior outside the creation path.

These are interoperability defects, not evidence that Grasshopper lacks an authentic
catalog. The correction should reuse the host's established machinery rather than
reimplementing it.

## Scope

The slice contains two gates:

1. A read-only Task 0 qualification of the installed Grasshopper component server.
2. A bounded production correction only after independent review of Task 0 evidence.

This version of the specification authorizes only a Task 0 implementation plan. It does
not authorize a complete production plan. After Task 0 review, amend this specification
to pin:

- the exact ordinary eligibility policy;
- whether native `FindObjects()` is adopted;
- the exact host provenance field names, representation, and nullability;
- any measured compatibility consequences.

Only that reviewed amendment may be converted into the production implementation plan.

The production correction is limited to:

- native-ranked `gh_library` search with a separate catalog-browse branch;
- additive truthful search evidence;
- GUID-safe and duplicate-name-safe `gh_batch_component_info` behavior;
- `gh_library.exact` parity through direct `ToolDispatcher` dispatch;
- suppression of unrelated knowledge hints for the two authoritative tools.

The frozen Opus control must run against the unchanged surface before the correction is
deployed. It is an affordance audit, not a prerequisite for choosing the implementation
algorithm and not proof that the current surface is adequate.

## Explicit non-goals

This slice adds no:

- embeddings, vector retrieval, reciprocal-rank fusion, or semantic reranking;
- custom alias catalog, synonym table, fuzzy matcher, or morphology engine;
- knowledge-store identity authority or recipe retrieval;
- DSPy optimization;
- harvested component registry or curated core-component allowlist;
- new component shorthand family;
- schema-driven compiler or semantic-graph behavior;
- Prime- or model-specific prompting;
- MCP session pooling, critic, scoring framework, or benchmark harness;
- canvas mutation during Task 0;
- cleanup of the two unrelated pre-existing knowledge-test failures.

## Current ownership and behavior

### Live catalog

`GrasshopperHandler.SearchLibrary()` obtains the live `GH_ComponentServer` and reads its
`ObjectProxies`. These include successfully registered native and installed third-party
components. Rook does not need a copied component catalog.

The current ordinary endpoint:

- iterates proxies in their existing enumeration order;
- stops once `results.Count >= limit`;
- excludes obsolete proxies;
- does not explicitly exclude hidden or quarantined proxies;
- applies case-insensitive category substring matching across both `Category` and
  `SubCategory`;
- uses a case-insensitive exact `Desc.Name` predicate when `exact=true`;
- otherwise performs a literal substring match across name, nickname, and description.

Because it stops before completing the scan, its returned list is not the complete
legacy match set.

### Installed native discovery machinery

The installed Grasshopper assembly at the baseline exposes:

```text
GH_ComponentServer.FindObjectByName(...)
GH_ComponentServer.FindObjects(...)
GH_ComponentServer.CompareProxies(...)
GH_ComponentServer.Aliases / AliasTargets(...)
```

Static inspection of the installed Rhino 8 Grasshopper build established:

- `FindObjects()` scans cached proxies, computes weighted native scores, incorporates
  Grasshopper-owned alias targets, sorts candidates, and only then applies its
  `maximumResults` bound;
- native name matches receive greater weight than nickname/keyword matches, which
  receive greater weight than description matches;
- `CompareProxies()` considers exposure and component names;
- native score values are host diagnostics, not stable cross-version product values;
- installed `FindObjectByName()` returns the first non-hidden, non-obsolete proxy whose
  `Desc.Name` matches. It does not preserve duplicate exact names and its installed
  behavior does not implement the category/subcategory qualification described by the
  API documentation.

Therefore `FindObjectByName()` cannot be the sole public exact-resolution path. Exact
public semantics require preserving every matching live type.

Relevant host API references:

- <https://developer.rhino3d.com/api/grasshopper/html/T_Grasshopper_Kernel_GH_ComponentServer.htm>
- <https://developer.rhino3d.com/api/grasshopper/html/M_Grasshopper_Kernel_GH_ComponentServer_FindObjectByName.htm>
- <https://developer.rhino3d.com/api/grasshopper/html/Overload_Grasshopper_Kernel_GH_ComponentServer_FindObjects.htm>
- <https://developer.rhino3d.com/api/grasshopper/html/M_Grasshopper_Kernel_GH_ComponentServer_CompareProxies.htm>

### Metadata

The managed `/gh/batch-component-info` endpoint already accepts component-type GUIDs and
reads proxy identity plus SDK-backed ports. The public MCP tool accepts names only,
resolves them through `UnifiedStore`, and falls back to the first exact library result.
That public name path can silently collapse native/third-party duplicate names.

### Creation and canvas identity

Component creation already refuses ambiguous exact name/nickname matches and directs
the caller to use a GUID. The discovery and metadata path should enforce the same
identity rule.

This does not change transaction or canvas shorthand:

```text
component type GUID
-> selected catalog identity used when ambiguity exists

T1, T2, ...
-> new instances inside one gh_edit batch

C1, C2, ...
-> existing instances in a gh_snapshot

gh_edit receipt
-> T* to C* and physical instance GUID correlation
```

Full type GUIDs are needed only when establishing ambiguous component-type identity.
Agents continue using compact `T*` and `C*` identifiers for graph construction and
subsequent editing.

## Task 0: installed native discovery qualification

Task 0 is a separately reviewed, read-only qualification. It makes no production or
test-code change and performs no model call or canvas mutation.

It may use one reviewed operator-only in-process probe against the installed
`GH_ComponentServer`. It must not add a product endpoint, registry, fixture authority,
or reusable benchmark framework.

### Candidate acquisition

For actual searches, Task 0 calls:

```text
FindObjects(
    terms = new[] { exact caller-supplied search string },
    maximumResults = ObjectProxies.Count,
    out proxies,
    out weights
)
```

Rook does not split, rewrite, stem, or expand the caller's search string.

Static inspection says `FindObjects()` already scans before truncation. The full bound
asks Grasshopper to retain its complete ranked candidate set so Rook can apply its
existing category and exact predicates without losing lower-ranked valid candidates.

Task 0 must not pass an empty query to `FindObjects()` and infer catalog-browse behavior.
Catalog browsing is qualified by direct live proxy enumeration.

### Fixed queries

The qualification records these fixed searches:

```text
Series
Range
Multiplication
Addition
Construct Point
Add
Point
```

It also records:

- at least one category-filtered case whose complete expected set includes candidates
  below the ordinary public limit;
- exact-name duplicate cases, including native/third-party collisions when installed;
- several currently installed third-party specimens from distinct plugin families;
- an empty-search catalog enumeration.

Third-party specimens are selected from the installed live catalog. For environmental
evidence, Task 0 records each specimen's component GUID, host-owned plugin/library or
assembly identity, plugin name, and version when the host exposes them. These specimens
do not become product fixtures, requirements, or an allowlist.

### Legacy comparison set

“Present in today's search” means every live proxy satisfying the complete current
ordinary predicate, not the prematurely truncated endpoint response.

For each applicable query, Task 0 independently evaluates across all live proxies:

```text
not obsolete
AND current case-insensitive Category/SubCategory substring predicate
AND (
    exact case-insensitive Desc.Name equality
    OR current case-insensitive Name/NickName/Description substring predicate
)
```

It compares that complete GUID set with the complete native `FindObjects()` candidate
set and classifies every GUID delta as obsolete, hidden, quarantined, another exposure
class, or otherwise unexplained.

### Required observations

Task 0 reports:

- exact Rhino and Grasshopper versions;
- live proxy count;
- complete legacy predicate match count;
- complete native candidate count;
- cold elapsed time for the first full native search;
- warm elapsed time for every fixed query;
- repeated timings sufficient to expose gross variance without becoming a benchmark;
- native ordered GUIDs and host scores;
- equal-score groups and the deterministic `CompareProxies`/GUID order;
- category-filter completeness;
- duplicate exact-name preservation;
- stable ordering across repeated calls;
- every eligibility delta with exposure/obsolete facts;
- third-party visibility and provenance evidence.

For provenance specifically, Task 0 inventories every usable host-owned source on both
proxy and instantiated metadata paths, including library/plugin identity, library GUID,
assembly identity, assembly version, or equivalent fields actually exposed by the
installed host. The report must propose one exact minimal field set that can be emitted
consistently by catalog candidates, successful GUID metadata, uniquely resolved name
metadata, and ambiguous-name candidates. It records field values, absence behavior, and
canonical string formatting rather than inventing Rook-maintained plugin labels.

Elapsed times are observations. Task 0 defines no hidden “fast enough” threshold and
does not authorize adoption automatically.

### Mandatory stop

Task 0 commits one bounded report at:

```text
docs/superpowers/reports/2026-08-08-grasshopper-native-component-discovery-qualification.md
```

The disposable probe and raw transient output do not become product code, a durable
catalog fixture, or a new evidence system. Task 0 then stops for independent review.

The review decides:

- whether full candidate retention has ordinary latency on the installed plugin-heavy
  catalog;
- whether native eligibility should replace or be reconciled with the current broader
  `not obsolete` policy;
- whether any unexplained third-party omission blocks adoption;
- whether native `FindObjects()` is adopted for ordinary search;
- the exact host provenance fields and representation required by the identity handoff.

After those decisions, this specification must be amended and independently reviewed.
Writing the production implementation plan before that amendment is prohibited.

If performance is unexpectedly expensive, investigate the measured bottleneck. Do not
invent repeated over-fetch loops, a parallel search index, or a custom ranking system.

## Provisional production behavior blocked on Task 0

The following behavior records the intended boundary but is not implementation-ready.
Every reference to an approved policy or Task 0-qualified field must be replaced by exact
language in the post-Task 0 specification amendment before production planning begins.

### Audit branch

```text
audit=true
-> execute existing audit enumeration and filtering
-> preserve existing audit JSON response shape
-> bypass ordinary native ranking
```

Task 0 does not authorize changing audit counts, filters, ordering, or component fields.

### Catalog branch

```text
audit=false
AND search absent
-> enumerate complete live proxy set
-> apply the independently approved eligibility policy
-> preserve current Category/SubCategory filter semantics
-> order by host CompareProxies priority
-> order equal proxies by GUID ordinal
-> apply public limit after ordering
```

Catalog components do not receive search metadata. There was no match operation.

### Search branch

```text
audit=false
AND search present
-> FindObjects(search terms, ObjectProxies.Count)
-> apply the independently approved eligibility policy
-> preserve current Category/SubCategory filter semantics
-> when exact=true, retain only case-insensitive exact Desc.Name matches
-> preserve every exact-name duplicate
-> order by native score descending
-> break equal native scores with host CompareProxies priority
-> break any remaining tie with GUID ordinal
-> apply public limit after filtering and ordering
```

Aliases may influence ordinary native search because Grasshopper owns them. Alias
targets never masquerade as exact-name matches.

No production rule prefers native components over third-party components. Ranking helps
discovery; GUID selection establishes identity.

### Category compatibility

Category filtering remains exactly:

```text
case-insensitive substring match against Category OR SubCategory
```

This slice does not narrow it to exact category names or reinterpret category hierarchy.

## `gh_library` response contract

Existing ordinary fields remain:

```text
count
components
```

Additive ordinary fields are:

```text
returnedCount
truncated
totalMatches       # only when the complete filtered set was computed
```

The equations are:

```text
count == returnedCount == components.length
```

When completeness is known:

```text
totalMatches == complete filtered-set size
truncated == returnedCount < totalMatches
```

When completeness is not proven, both `totalMatches` and `truncated` are omitted.
`truncated=false` is never emitted as a guess. Under the proposed full search and
catalog-enumeration paths, completeness should ordinarily be known.

Actual search results additionally carry:

```text
nativeScore
matchSource: exact_name | native_search
```

`nativeScore` is the exact host-provided diagnostic score for that call. Clients may
observe it but must not treat its numerical scale as stable across Grasshopper versions.
Ordering is the product behavior.

`matchSource=exact_name` means Rook applied case-insensitive exact `Desc.Name` equality.
It is not inferred from the numerical native score. Other actual search results use
`native_search`. Catalog browsing omits both fields.

Every catalog/search component also carries the exact host provenance fields selected in
the post-Task 0 specification amendment. Those fields are identity evidence, not ranking
inputs. The same field names and value semantics must be used by metadata outcomes.

The `audit=true` response shape remains unchanged and receives none of these additions.

## `gh_batch_component_info` identity contract

The public tool accepts exactly one selector family:

```text
names only
OR
guids only
```

Requests containing both nonempty `names` and nonempty `guids` refuse before target
contact. Requests containing neither refuse under the existing public validation
boundary.

### GUID input

GUID requests bypass `UnifiedStore` and call the authoritative managed metadata endpoint
directly.

The result preserves deterministic request order and returns one identified outcome for
every requested GUID, including duplicate requests, invalid GUIDs, not-found GUIDs,
uninstantiable types, and successful metadata. No requested GUID silently disappears.

Every successful GUID outcome carries the exact host provenance fields selected after
Task 0, using the same names and semantics as `gh_library` candidates.

### Name input

Names remain supported for compatibility, but knowledge no longer resolves type
identity. For each requested name, Rook performs a live case-insensitive exact
`Desc.Name` lookup over the complete proxy set satisfying the eligibility policy
approved after Task 0:

```text
zero exact matches
-> explicit not_found outcome

one exact match
-> resolve that GUID
-> return authoritative metadata

multiple exact matches
-> explicit ambiguous_name outcome
-> include every candidate
-> perform no first-candidate selection
```

The result preserves original name request order and returns exactly one outcome per
requested name, including repeated identical names and mixed batches containing unique,
missing, and ambiguous items. A unique item may proceed to authoritative metadata even
when another item in the same batch is ambiguous or missing. An ambiguous item prevents
metadata contact only for that item.

Each ambiguous candidate includes:

```text
name
nickname
category
subcategory
guid
the exact Task 0-qualified host provenance fields
```

Candidate ordering is deterministic and never collapses duplicate names. Knowledge-store
ordering cannot influence identity.

Unique name requests continue to work. Previously unsafe ambiguous requests change from
nondeterministic selection to a truthful refusal requiring a selected GUID.

## Creation compatibility

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

Existing `gh_edit` temporary identifiers, snapshot short identifiers, flow syntax, and
receipt correlation remain unchanged. Neither `gh_edit` nor `gh_snapshot` acquires a new
lookup or identity layer.

## Knowledge and dispatcher corrections

`gh_library` and `gh_batch_component_info` are authoritative live discovery tools.
`KnowledgeInjector` must skip both tools rather than adding unrelated canvas-size,
mesh-validity, recipe, or other learned hints.

This does not remove knowledge as future advisory context. A later retrieval slice may
propose semantic candidates, but it may not alter native ranking, component GUIDs, port
metadata, or ambiguity decisions.

The direct ChatRunner `ToolDispatcher` transformation must preserve the existing
`exact` argument exactly as canonical MCP dispatch already does.

These contracts apply through:

- direct public MCP calls;
- contained targets invoked through `rook_tools_call`;
- direct ChatRunner tools where already supported.

No second capability catalog or dispatch table is introduced.

## Frozen Opus control definition

The control is pinned to this exact future artifact root:

```text
C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-opus-control
```

Its reviewed row path is:

```text
C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-opus-control/operator/row.json
```

The row and isolated model configuration must pin:

```text
model: anthropic/claude-opus-4-6
provider: anthropic
modelId: claude-opus-4-6
api: anthropic-messages
credential-free base URL: https://api.anthropic.com
intent: Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.
```

The control reuses the Prime V7 public capability surface and reviewed execution method:

```text
source artifact: C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v7
control skill: C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-opus-control/agent/skills/prime-execute-grasshopper/SKILL.md
control checkpoint: C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-opus-control/agent/skills/prime-execute-grasshopper/references/checkpoint-protocol.md
control adapter: C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-opus-control/agent/skills/rook-full/src/rook_full/__init__.py
skill SHA-256: 0F7C8D1F2D612FFB7522469C4E3D467985E8872585CA3C18DF9B46BD1A84D36E
checkpoint SHA-256: 76A7C0CFF04DEF83A75519A546AC812804AC32BBF30CC14609A6D52950248964
rook_full adapter SHA-256: E7577F0EC8A9B504712BC73290BB8F4C673E9677AEF952CFBFC346F206A62996
```

The skill body, checkpoint, adapter transport, `search/read/call` public surface, natural
intent, full Rook profile, evidence rules, and final-inspection request remain unchanged.
Only the isolated provider/model configuration, model-custody checks, sibling paths, and
fresh reviewed Rhino target differ from V7.

Before contact, the complete sibling manifest and row hash must be independently
reviewed. The fresh row carries the exact panel-locked PID, native port, and document
serial for an empty disposable canvas. This target-dependent row hash cannot be invented
in the design document; the exact artifact path and static capability hashes above are
the durable control identity.

The evidence contract is:

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

Before deploying the production correction, run this control against the unchanged
discovery surface under separate authorization.

Record at minimum:

- its semantic plan before the first mutation;
- every discovery query and selected option;
- rank of the ultimately selected component;
- irrelevant results consumed;
- whether it discovers `Series`;
- metadata/schema reads and invalid calls;
- time and cumulative tokens before first mutation;
- edits, snapshots, partial results, and corrections;
- final mechanical outcome;
- final semantic fidelity separately from compilation or clean diagnostics.

Opus success demonstrates compensation ability only. It does not invalidate measured
discovery defects or authorize skipping the correction.

## Verification requirements

### Managed discovery tests

Use causal proxy fixtures to prove:

- `audit=true` bypasses ordinary ranking and preserves its response shape;
- absent search uses complete enumeration, category filtering, `CompareProxies`, GUID
  tie-breaking, and limit-after-ordering;
- present search consumes native ranked candidates and limits only after filters;
- current category/subcategory substring behavior is preserved;
- exact mode is case-insensitive `Desc.Name` equality;
- every exact duplicate survives, including native/third-party same-name candidates;
- aliases can influence ordinary native search but not exact matches;
- count equations and conditional completeness fields are exact;
- native scores remain observational fields;
- third-party proxies are not excluded by a core allowlist;
- the independently approved eligibility policy is implemented exactly.

Do not make installed third-party specimens durable product fixtures. Tests use synthetic
causal proxies representing native and third-party collisions.

### Metadata tests

Prove:

- GUID-only requests call authoritative metadata directly;
- requests containing both selector families refuse before target contact;
- every GUID produces one ordered outcome, including not found;
- zero, one, and multiple live exact-name matches produce the required outcomes;
- every requested name produces one ordered outcome, including duplicates and mixed
  unique/missing/ambiguous batches;
- ambiguity blocks metadata only for the ambiguous item;
- ambiguous candidates all survive and remain distinguishable;
- catalog, GUID metadata, unique-name metadata, and ambiguity candidates expose the same
  exact Task 0-qualified provenance fields;
- GUID lookup resolves each same-name native/third-party candidate independently;
- knowledge-store ordering cannot influence name identity;
- ambiguous name creation remains refused.

### Python boundary tests

Prove through direct MCP and `rook_tools_call` paths:

- `gh_library` search arguments and additive results pass through unchanged;
- `gh_batch_component_info` names/GUIDs validation is identical;
- structured MCP success/failure projection remains owned by the existing public handler;
- no gateway double wrapping is introduced;
- both authoritative tools bypass knowledge injection;
- the direct `ToolDispatcher` preserves `exact`;
- the two existing unrelated knowledge-test failures keep their recorded identities and
  signatures, with no new failures.

## Production module boundary

The expected production scope is limited to the existing owners:

```text
src/Rook/Handlers/GrasshopperHandler.cs
mcp_server/src/rook/server.py
mcp_server/src/rook/agent/tool_dispatcher.py
mcp_server/src/rook/learning/knowledge_injector.py
```

Focused tests and the Task 0 evidence artifact may be added. No new production module,
registry, search service, result framework, or identity abstraction is expected.

If the implementation requires broader machinery, stop and reconsider the boundary.

## Failure behavior

- Failure to obtain the live component server returns the existing tool failure shape.
- Unexpected native-search failure returns a truthful failure; it does not silently fall
  back to the old registration-order algorithm.
- Ambiguous name identity refuses selection and reports candidates.
- Missing GUID identity returns an explicit per-request failure.
- Metadata instantiation failure remains a per-request outcome.
- Task 0 unexplained candidate loss or unexpectedly expensive full retention blocks
  adoption pending review.
- No retry, hidden fallback, knowledge substitution, or automatic native preference is
  introduced.

## Claims

After Task 0 and a successful implementation, this slice may claim:

- ordinary component search uses Grasshopper's native ranked catalog and aliases;
- Rook preserves its public category and exact-name semantics;
- results are limited after complete filtering and ordering;
- native and installed third-party components remain discoverable subject to the
  independently approved eligibility policy;
- duplicate component-type names cannot silently choose the wrong implementation;
- a selected catalog GUID flows directly into authoritative SDK metadata;
- agents retain compact `T*` and `C*` identities for graph work;
- unrelated knowledge hints no longer modify these authoritative results.

It may not claim:

- arbitrary semantic retrieval or typo recovery;
- stable native-score values across Grasshopper versions;
- visibility of plugins that failed to load or register;
- automatic preference for core or third-party components;
- that metadata proves runtime semantic correctness;
- improved model reasoning independently of a controlled rerun;
- knowledge or DSPy effectiveness.

## Anti-quagmire stop conditions

Stop before implementation expansion if:

- Task 0 requires a new product endpoint or persistent catalog;
- native search cannot preserve installed third-party candidates without a parallel index;
- preserving category completeness appears to require repeated speculative over-fetching;
- the correction requires embeddings, fuzzy matching, custom aliases, or knowledge
  migration;
- a new GUID or short-ID family is proposed;
- `gh_edit` or `gh_snapshot` identity machinery must change;
- more than the four existing production owners need material changes;
- the Opus or later Qwen result is used to introduce witness-specific ranking or prompts.

The KISS boundary is:

> One native search owner, one authoritative type GUID, one authoritative metadata owner,
> existing compact canvas identities, and truthful ambiguity.
