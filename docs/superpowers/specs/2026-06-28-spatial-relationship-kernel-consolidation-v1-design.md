# Spatial Relationship Kernel Consolidation v1 - design

> **Current north star (2026-06-28):** This slice spec records the kernel consolidation proof.
> For the current canonical spatial-intelligence architecture, use
> `docs/rook_docs/SPATIAL_INTELLIGENCE_NORTH_STAR.md`.

> Status (2026-06-28): DESIGN - approved direction, written for review.
> Branch/worktree: `codex/spatial-relationship-kernel-consolidation-v1` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on `codex/relationship-geometry-evidence-v1`. Do not add more work to
> `codex/relationship-geometry-evidence-v1` unless review feedback requires it.

## 1. Reviewer backfill

The recent graph work built several useful pieces:

- Authored Graph Schema v2 defines domain-neutral persisted graph/user-text records:
  `object`, `feature`, `relationship`, `relationship_type`, `contact_kind`, `provenance`,
  `confidence`, and `status`.
- `scene_project_relationship_facts` hydrates authored Rhino user text and projects
  `relationship_fact_v1` owner-object-to-owner-object edges into `SceneGraphAnalytics.graph`.
- `scene_semantic_relationships` is a raw object-centric inspector over those projected edges.
- `scene_object_semantic_context` is a bounded card/view layer over the raw inspector.
- `scene_relationship_profile` supplies vocabulary labels, inverse names, categories, and
  contact-kind labels without changing fact truth.
- `scene_relationship_evidence` measures feature-marker-position distance for already-projected
  relationship facts. It is read-only, feature-marker-only, and does not infer or mutate facts.
- `scene_exact_neighbors` / `exact_projection.py` project OCCT exact adjacency into
  `adjacent_exact` edges with `provenance="occt"` and shared topology payloads.
- `containment_refinement.py` has an older derived semantic refinement path with its own evidence
  and verdict vocabulary.
- The fuzzy scenegraph still produces broad spatial observations such as `near`, `adjacent`,
  `contains`, and related heuristic edges.

The pieces work, but their names and outputs can imply parallel worldviews:

```text
scene graph
+ semantic graph
+ evidence tool
+ profile layer
+ exact topology layer
+ refinement layer
```

This slice consolidates the architecture into one spine before more geometry evidence or inference
work is added.

## 2. Thesis

Rook should reason about physical models through one spatial relationship spine:

```text
runtime object
-> authored or detected feature / interface
-> RelationshipClaim
-> RelationshipEvidence
-> RelationshipVerdict
-> view / context / action
```

The key triangle is:

```text
RelationshipClaim = semantic claim
RelationshipEvidence = measured support, contradiction, or missing proof
InterfaceRecord = physical/topological contact, overlap, bridge, penetration, or adjacency that
                  evidence can cite
```

This explicitly separates semantic meaning from physical proof:

- `connects`, `supports`, `penetrates`, `hosted_by`, and `bounded_by` are claim semantics.
- `feature_marker_position_distance`, `adjacent_exact`, `brep_intersection`, and future OCCT
  shared-topology methods are evidence methods.
- A claim can be accepted by provenance/status while still physically unverified.
- Evidence can support or contradict a claim without changing claim truth unless a later explicit
  inference or review slice writes a new claim/status.

## 3. Meaning of "kernel"

In this slice, `kernel` means a model and contract boundary, not a large new module.

This spec does not authorize a broad `kernel.py` that absorbs projection, profiles, cards, exact
adjacency, containment refinement, and scenegraph code. The correct near-term implementation is a
small adapter/reporting module that proves existing systems can speak through the same
claim/evidence/verdict contract.

The consolidation goal is:

```text
one relationship model
one evidence model
multiple evidence sources
multiple views over the same core
```

The anti-goal is:

```text
more stacked tools that each define their own relationship truth vocabulary
```

## 4. Canonical vocabulary

### Runtime Object

A selectable/runtime Rhino object occurrence represented as a scenegraph node. Normal objects and
block instances are runtime objects. Block definitions are not runtime objects in this vocabulary
unless they appear as explicit runtime nodes in a future slice.

### Feature

An addressable semantic or geometric attachment point on a runtime object, such as:

```text
column_01.top_point
slab_01.underside_region
wall_01.host_region
robot_elbow_joint.point
```

Features may be authored or detected. Feature marker geometry is an implementation aid, not proof
of physical contact.

### InterfaceRecord

A physical/topological interface observed or asserted between runtime objects or features.

Examples:

```text
shared_face
shared_edge
point_touch
line_region_intersection
penetration_volume
clearance_gap
explicit_connector
```

An `InterfaceRecord` can come from OCCT, Rhino geometry measurement, imported BIM topology,
Topologic-like graph extraction, or authored connector metadata. It is the bridge between geometry
and semantic relationship claims.

### RelationshipClaim

A proposed semantic relationship between owner objects, usually with feature endpoints:

```text
column_01.top_point supports slab_01.underside_region
door_01.body hosted_by wall_01.host_region
duct_01.centerline penetrates wall_01.penetration_region
```

Current `relationship_fact_v1` projected edges are canonical `RelationshipClaim` records in v1.
They are claims, not proof.

Required claim fields:

```text
relationshipClaimId
relationshipType
fromObjectId
toObjectId
fromFeature
toFeature
contactKind
provenance
confidence
status
graphSource
graphRevision
pose
```

Current edge field aliases such as `relationshipFactId` and `relationship` may remain as storage
fields for now, but docs and new code should frame them as claim fields.

### RelationshipEvidence

Measured, imported, or authored support for or against a claim.

Required evidence fields:

```text
relationshipClaimId
evidenceId
kind
method
source
strength
polarity
status
measures
interfaceRecordIds
diagnostics
```

`polarity` values:

```text
supports
contradicts
neutral
missing
```

`status` values:

```text
measured
missing
failed
not_applicable
```

Evidence does not create, accept, reject, or mutate claims by itself.

### RelationshipVerdict

A derived assessment of a claim after considering available evidence and profile obligations.

Canonical verdict values:

```text
satisfied
contradicted
unverified
not_applicable
```

These are intentionally not claim statuses. Claim status still expresses semantic acceptance or
workflow state, such as `accepted` or future review states. Verdict expresses physical/evidentiary
support for a claim.

### Profile

Project vocabulary and interpretation hints. Profiles own:

```text
labels
inverse labels
categories
contact-kind display
future ontology mappings
future evidence obligations
```

Profiles do not prove truth. A profile may later say that `supports` expects an
`exact_topology` or `explicit_connector` evidence strength, but it must not directly fabricate that
evidence.

### View

Inspector/card/context formatting over claims, evidence, and verdicts. Views are disposable
presentation surfaces and must not become architecture.

## 5. Evidence strength scale

V1 uses a deliberately simple ordered evidence-strength scale:

```text
none
marker_hint
bbox_observation
exact_topology
explicit_connector
```

Meaning:

| Strength | Meaning | Examples |
|---|---|---|
| `none` | No physical evidence is available. | Missing feature position, no measured interface. |
| `marker_hint` | Authored/debug marker positions suggest proximity. | `feature_marker_position_distance`. |
| `bbox_observation` | Bounding-box or broad-phase geometry suggests possible contact/containment. | Fuzzy `near`, `adjacent`, bbox `contains`. |
| `exact_topology` | Exact geometric/topological computation found or refuted a physical interface. | OCCT `adjacent_exact`, shared face/edge, exact intersection. |
| `explicit_connector` | A domain system or authored connector explicitly represents a physical/topological connection. | Revit connector, MEP port, assembly joint connector. |

The scale is ordered, but not probabilistic. It is for reporting strongest available evidence and
for deciding whether a claim has enough support to evaluate. It is not automatic conflict
resolution. For example, an explicit connector record and an exact-topology contradiction can
coexist; a later verdict rule must handle that conflict deterministically. Do not implement
`higher strength wins` as a default rule.

The scale prevents feature-marker coincidence from being treated as equivalent to shared topology
or explicit connector metadata.

V1 verdict logic should be conservative:

- `marker_hint` can support `unverified` claims, but should not by itself produce `satisfied` for
  physical contact claims unless a profile explicitly marks marker evidence as sufficient.
- `bbox_observation` can suggest candidates or weak support, but cannot prove contact.
- `exact_topology` can satisfy or contradict contact-like claims when the evidence method applies.
- `explicit_connector` can satisfy connector-like claims when connector identity and endpoints
  match.

## 6. Hard boundaries

These are non-negotiable for the next implementation work:

- Claims do not prove contact.
- Evidence does not create claims unless a future inference slice explicitly does that.
- Evidence does not mutate claim status.
- Claim type and evidence method are separate fields.
- Feature-marker coincidence is weak evidence, not physical proof.
- Fuzzy scenegraph edges are observations/candidates, not claims and not proof.
- OCCT/shared topology is a strong physical evidence source and must feed the same evidence
  contract as feature-marker evidence.
- Absence of exact evidence is not refutation. Missing `adjacent_exact` or missing exact projection
  data means `unverified`, not `contradicted`.
- `contradicted` requires an explicit evaluated/refuted evidence record for the exact
  claim/object/interface pair being evaluated.
- Views/cards/contexts format the model; they are not the model.
- Profiles define vocabulary and future obligations; they do not create truth.
- `kernel` is a contract boundary; do not build a monolithic kernel module.

## 7. Existing surface decision table

| Surface | Decision | Canonical framing | Notes |
|---|---|---|---|
| `relationship_fact_v1` edge | Keep, reframe | `RelationshipClaim` | Keep storage shape for now; docs and new code should treat it as a claim. |
| `RelationshipFact` dataclass | Keep, likely rename later | `RelationshipClaim` model | A future rename is desirable, but not required in the first consolidation proof. |
| `scene_project_relationship_facts` | Keep | Authored-claim projection | Name can remain temporarily; docs should state it emits claims. |
| `scene_semantic_relationships` | Keep | Raw claim inspector | Useful selected-object read model; must not imply physical truth. |
| `scene_object_semantic_context` | Keep | View/card layer | Presentation mechanics only: grouping, truncation, profile labels, samples. |
| `scene_relationship_profile` | Keep | Vocabulary/obligation profile | Labels/categories now; evidence obligations later. |
| `scene_relationship_evidence` | Keep, narrow/reframe | Feature-marker evidence source | Current name is broad. In docs, call it feature-marker evidence v1. A later umbrella evidence query may subsume it. |
| `relationship_geometry_evidence.py` | Keep as source adapter | `marker_hint` evidence adapter | Do not let it become the general evidence kernel. |
| `adjacent_exact` | Keep, integrate | OCCT exact-topology evidence source | Should feed `RelationshipEvidence` / `InterfaceRecord`, not remain a separate worldview. |
| `scene_exact_neighbors` | Keep | Explicit exact-topology projection trigger | Its output should be reusable by evidence/verdict evaluation. |
| `containment_refinement.py` | Keep provisional/legacy-adjacent | Derived semantic refinement | Must be audited later into claim/evidence/verdict terms; do not expand it as a parallel verdict system. |
| Fuzzy scenegraph edges (`near`, `adjacent`, `contains`, broad `intersects`) | Keep as observations | `bbox_observation` / candidate hints | Useful for search and candidate generation; not canonical claims or proof. |
| `scene_context` relationship wording | Keep as view | Text formatting | Should eventually include claim/evidence/verdict summaries through view code, not define semantics. |
| Architectural and Pearson fixtures | Keep | Test data | Domain vocabulary is allowed in fixtures/tests/profiles. |

## 8. Verdict obligations in v1

The first verdict implementation should be intentionally small and explicit.

Input:

```text
already-projected RelationshipClaim edges
+ available evidence records from feature markers and/or exact topology
+ optional profile obligation hints when present
```

Output per claim:

```json
{
  "relationshipClaimId": "...",
  "relationshipType": "supports",
  "verdict": "satisfied",
  "reason": "exact_topology_supports_contact",
  "strongestEvidenceStrength": "exact_topology",
  "evidence": [...]
}
```

Initial verdict rules:

| Condition | Verdict |
|---|---|
| Claim has applicable `exact_topology` evidence supporting the required interface | `satisfied` |
| Claim has applicable explicit `exact_topology` refutation for the required interface | `contradicted` |
| Claim has only `marker_hint` or `bbox_observation` evidence | `unverified` |
| Claim has no relevant evidence | `unverified` |
| Claim type/contact kind has no defined physical obligation in v1 | `not_applicable` |

Physical obligation means the claim/profile/contact kind expects a physical interface. V1 is scoped
specifically to OCCT exact adjacency/shared-topology evidence. It must not pretend that
`adjacent_exact` is applicable to every physical relationship word.

V1 applicability table:

| Claim/contact shape | `adjacent_exact` applicability in v1 | Default verdict posture |
|---|---|---|
| `connects` with point/edge/face contact-like `contactKind` | Applicable when the claim/profile says physical contact is expected. | Exact support can satisfy; explicit exact refutation can contradict. |
| `supports` with contact-like `contactKind` | Applicable only when fixture/profile/claim metadata says support is by direct contact. | Exact support can satisfy; explicit exact refutation can contradict. |
| Generic direct contact-like relationship with face/region contact | Applicable when exact adjacency is a meaningful interface for the contact kind. | Exact support can satisfy; explicit exact refutation can contradict. |
| `penetrates` | Not applicable in v1. Shared-face adjacency is not penetration evidence. | `not_applicable` unless a future penetration/intersection method is present. |
| `hosted_by` | Not applicable in v1. Hosting can be semantic/parametric without physical adjacency. | `not_applicable` unless a future host/opening-specific method is present. |
| Relationship/contact kind with unclear physical obligation | Not applicable in v1. | `not_applicable`. |

For every applicable row, lack of an `adjacent_exact` edge is still not enough to contradict the
claim. Contradiction requires an explicit evaluated exact refutation, such as a route/refinement
payload or annotation that says the specific evaluated pair has no required exact interface.

## 9. Next implementation proof

The first implementation after this spec should be:

```text
OCCT adjacent_exact -> unified evidence/verdict adapter for already-projected claims
```

It should be small:

- one focused module or test-support module, not a large kernel rewrite;
- consumes existing projected `relationship_fact_v1` claim edges;
- consumes existing `adjacent_exact` edges already projected by `scene_exact_neighbors`;
- consumes exact refutation signals already present from exact projection, such as
  `exact_status="exact_refuted"` annotations on broad-phase edges or explicit refutation payloads
  returned by the exact projection path;
- optionally consumes feature-marker evidence as weak `marker_hint`;
- emits `RelationshipEvidence` and `RelationshipVerdict` records in the new canonical shape;
- does not call OCCT by itself unless an explicit caller already requested exact projection;
- does not infer new claims;
- does not mutate Rhino;
- does not mutate claim status;
- does not add a display/card layer;
- does not refactor containment refinement.

The proof must demonstrate:

```text
authored claim + no evidence -> unverified
authored claim + marker_hint only -> unverified
authored claim + exact topology support -> satisfied
authored claim + exact topology refutation -> contradicted
claim with no v1 physical obligation -> not_applicable
```

This is the smallest useful bridge between today’s semantic graph work and the earlier OCCT exact
adjacency work.

## 10. Future migration path

After the OCCT adapter proof, likely follow-up slices are:

1. Rename/refactor public docs and internal model names from `RelationshipFact` toward
   `RelationshipClaim`.
2. Add profile evidence obligations, such as:

   ```json
   {
     "relationships": {
       "supports": {
         "requiredEvidenceStrength": "exact_topology",
         "acceptableEvidenceMethods": ["adjacent_exact", "explicit_connector"]
       }
     }
   }
   ```

3. Audit `containment_refinement.py` and convert its private evidence/verdict vocabulary into the
   shared evidence/verdict contract.
4. Add candidate inference only after the claim/evidence/verdict contract is stable.
5. Add view/card enrichment for verdict summaries after the kernel contract has tests.

## 11. Testing requirements for the next implementation plan

The next implementation plan should include pure tests before any live Rhino gate:

- `relationship_fact_v1` projected edge is normalized to a `RelationshipClaim`.
- feature-marker distance evidence is normalized to `strength="marker_hint"`.
- existing `adjacent_exact` edge is normalized to `strength="exact_topology"` and creates an
  `InterfaceRecord`.
- claim with no evidence returns `verdict="unverified"`.
- claim with marker evidence only returns `verdict="unverified"`.
- contact-like claim with matching exact topology returns `verdict="satisfied"`.
- contact-like claim with exact topology refutation returns `verdict="contradicted"`.
- semantic-only claim with no v1 physical obligation returns `verdict="not_applicable"`.
- claim type and evidence method are stored as separate fields.
- view/card modules do not become dependencies of the verdict module.

Live tests should be optional/skippable and should only come after pure tests pass. They may reuse
the architectural fixture if exact adjacency can be projected cheaply for a small pair set.

## 12. Non-goals

This consolidation slice must not:

- add inference;
- add a new display surface;
- add CAD plan parsing;
- add IFC/BOT/Brick/RDF integration;
- add TopologicPy as a dependency;
- add broad owner-geometry inspection beyond the next explicit OCCT adapter proof;
- rename all existing APIs immediately;
- refactor `scene_graph.py` broadly;
- collapse all relationship modules into one large file.

## 13. Success criteria

This spec succeeds if a reviewer can answer:

- Which current surfaces are claims, evidence sources, verdict logic, profiles, or views?
- Which surfaces are canonical, provisional, or legacy-adjacent?
- Why feature-marker distance is weaker than OCCT exact topology?
- Why `supports` is a claim type while `adjacent_exact` is an evidence method?
- What the next implementation proof is and what it must not do?

The implementation after this spec succeeds only when exact topology evidence and authored claims
produce one unified verdict report without adding a new parallel scenegraph worldview.
