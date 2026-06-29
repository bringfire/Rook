# Rook Spatial Intelligence North Star

> Status (2026-06-28): Canonical framing for current spatial-intelligence work.
>
> Older dated spatial-intelligence documents remain valuable historical evidence and design
> context. When they conflict with this document, use this document as the current north star.

## 1. Thesis

Spatial intelligence in Rook means:

```text
claims about physical relationships
+ measured geometric/topological evidence
-> explicit verdicts that agents and tools can inspect
```

The core correction is simple:

```text
RelationshipClaim is not proof.
RelationshipEvidence is not claim creation.
RelationshipVerdict is not claim status.
```

Rook should reason about physical models through one spine, not through parallel relationship
vocabularies:

```text
RuntimeObject
-> Feature / Interface
-> RelationshipClaim
-> RelationshipEvidence
-> InterfaceRecord
-> RelationshipVerdict
-> View / Action
```

## 2. How to Use This Doc

When designing a new spatial feature, first classify it as one of these roles:

- claim source
- evidence source
- verdict evaluator
- profile / vocabulary
- view / action
- observation / candidate source

If a feature cannot fit one of those roles, challenge the design. It may be creating a parallel
relationship layer instead of strengthening the shared spine.

Use the role before choosing a name. For example:

- `supports` is a claim type.
- `adjacent_exact` is an evidence method.
- `accepted` is claim workflow status.
- `satisfied` is an evidence verdict.
- `structural` is profile/category vocabulary.
- `near` is an observation or candidate hint.

## 3. Canonical Spine

### RuntimeObject

A selectable runtime object occurrence represented in the scenegraph. Normal Rhino objects and
block instances are runtime objects. Block definitions are not runtime objects unless a future
slice gives them explicit runtime nodes.

### Feature

An addressable semantic or geometric attachment point on a runtime object:

```text
column_01.top_point
slab_01.underside_region
wall_01.host_region
robot_elbow_joint.point
```

Features may be authored, imported, detected, or inferred. Feature marker geometry is an
implementation aid. Marker coincidence is not physical proof.

### InterfaceRecord

A physical or topological interface observed or asserted between objects or features:

```text
shared_face
shared_edge
point_touch
line_region_intersection
penetration_volume
clearance_gap
explicit_connector
```

An interface record is the bridge between geometry/topology and semantic claims.

### RelationshipClaim

A proposed semantic relationship between runtime objects, usually with feature endpoints:

```text
column_01.top_point supports slab_01.underside_region
door_01.body hosted_by wall_01.host_region
duct_01.centerline penetrates wall_01.penetration_region
```

Claims can be authored, imported, or inferred later. A claim may be semantically accepted while
still physically unverified.

Current `relationship_fact_v1` projected edges are RelationshipClaims. The name is historical.

### RelationshipEvidence

Measured, imported, or authored support for or against a claim.

Examples:

- feature-marker distance
- OCCT shared topology
- exact intersection
- Revit connector identity
- future penetration volume measurement

Evidence has a method, source, strength, polarity, status, measures, diagnostics, and cited
interface records. Evidence does not create, accept, reject, or mutate claims by itself.

### RelationshipVerdict

A derived evidentiary assessment of a claim.

Canonical values:

```text
satisfied
contradicted
unverified
not_applicable
```

Verdicts are not claim statuses. Claim status expresses workflow or provenance state, such as
`accepted`. Verdict expresses whether available evidence supports the physical obligation of the
claim.

### View / Action

Inspectors, cards, context text, reports, selection tools, and future UI overlays are views or
actions over the model. They must not define truth.

## 4. Role Map

| System | Role | Current framing |
|---|---|---|
| Authored graph user text | Claim source | Emits RelationshipClaims from object/feature/relationship records. |
| `scene_project_relationship_facts` | Claim projection | Projects authored claims into the Python scenegraph. |
| `relationship_fact_v1` | RelationshipClaim storage edge | Keep for now, but frame as claims, not facts/proof. |
| OCCT / exact adjacency | Evidence source | Produces exact-topology support or refutation. |
| `adjacent_exact` | Evidence method | Strong but scoped owner-pair topology evidence; requires OCCT provenance. |
| Feature-marker distance | Evidence source | Weak `marker_hint`, useful for debugging and authored intent. |
| Fuzzy scenegraph edges | Observation / candidate source | `near`, broad `adjacent`, bbox `contains`, and bbox `intersects` are hints, not proof. |
| Relationship profile | Profile / vocabulary | Labels, inverse labels, categories, contact-kind display, future obligations. |
| Semantic inspector | Raw claim inspector | Structured selected-object view over projected claims. |
| Object semantic context card | View | Grouping, truncation, samples, profile-enriched display. |
| `scene_context` text | View | Agent-readable formatting, not canonical semantics. |
| Containment refinement | Provisional evaluator | Must be audited into claim/evidence/verdict vocabulary before expansion. |
| TopologicPy | Conceptual precedent | Useful mental model; not a dependency and not imported. |

## 5. Evidence Strength

V1 uses this ordered strength scale:

```text
none
marker_hint
bbox_observation
exact_topology
explicit_connector
```

The order is for reporting and evaluation guidance. It is not automatic conflict resolution.
A stronger category does not simply erase a weaker record. Verdict rules decide conflicts.

| Strength | Meaning | Examples |
|---|---|---|
| `none` | No relevant evidence is available. | Missing measured interface. |
| `marker_hint` | Authored/debug marker positions suggest proximity. | `feature_marker_position_distance`. |
| `bbox_observation` | Broad geometry suggests possible contact. | Fuzzy `near`, broad `adjacent`, bbox `contains`. |
| `exact_topology` | Exact geometric/topological computation found or refuted an interface. | OCCT `adjacent_exact`, exact shared face, exact intersection. |
| `explicit_connector` | A domain system or authored connector explicitly represents a physical connection. | Revit connector, MEP port, assembly joint connector. |

## 6. Non-Negotiables

- Claims are not proof.
- Evidence is not claim creation.
- Verdicts are not claim statuses.
- Missing evidence is not contradiction.
- `contradicted` requires explicit evaluated refutation for the relevant claim/object/interface.
- Marker coincidence is weak evidence.
- Bounding-box observations are hints and candidates.
- Exact topology is strong but scoped. It must state what it actually proves.
- `adjacent_exact` proves owner-pair exact topology in v1, not feature-interface contact.
- Views never define truth.
- Profiles define vocabulary and obligations; they do not fabricate evidence.
- Claim type and evidence method are separate fields.
- Domain words belong in profiles, fixture data, authored graphs, and tests, not parser-facing core
  keys.
- Rook should not maintain parallel relationship vocabularies.

## 7. Decision Table

| Surface | Decision | Canonical role | Notes |
|---|---|---|---|
| `relationship_fact_v1` | Keep, reframe | RelationshipClaim edge | Historical name; do not treat as proof. |
| `RelationshipFact` model naming | Keep temporarily, rename later | RelationshipClaim | Rename only when it reduces confusion without destabilizing active slices. |
| `scene_project_relationship_facts` | Keep | Authored-claim projection | Documentation should say it projects claims. |
| `scene_semantic_relationships` | Keep | Raw claim inspector | Structured selected-object claim query. |
| `scene_object_semantic_context` | Keep | View/card layer | Presentation mechanics only. |
| `scene_relationship_profile` | Keep | Vocabulary/profile layer | Future home for data-defined evidence obligations. |
| `scene_relationship_evidence` | Keep, narrow wording | Marker-hint evidence source | Current implementation is feature-marker-position evidence, not general truth. |
| `relationship_geometry_evidence.py` | Keep as adapter | Marker-hint evidence adapter | Do not let it become the broad evidence kernel. |
| `relationship_kernel.py` | Keep internal | Claim/evidence/verdict read model | Internal proof of the spine; no public MCP surface in v1. |
| `adjacent_exact` | Keep | Exact-topology evidence method | Requires OCCT provenance to count as exact topology evidence. |
| `scene_exact_neighbors` | Keep | Exact-topology projection trigger | Produces evidence source data; not a claim source. |
| Fuzzy scenegraph edges | Keep | Observation/candidate source | Useful for search, broad phase, and candidate generation. |
| `containment_refinement.py` | Keep provisional | Legacy-adjacent evaluator | Audit into shared vocabulary before expanding. |
| Cards/context text | Keep | View | Must consume claims/evidence/verdicts, not define them. |
| Pearson and architectural fixtures | Keep | Test data | Domain vocabulary is allowed in fixtures. |

## 8. Roadmap

Near-term work should consolidate before expanding.

1. Keep the relationship kernel report internal and use it to validate the contract.
2. Adopt kernel terminology where existing tools discuss relationship evidence.
3. Move profile obligations from future idea to data-defined contract.
4. Audit containment refinement into claim/evidence/verdict vocabulary.
5. Add stronger physical evidence methods only after obligations are explicit.
6. Start inference only after authored/imported claims, evidence, and verdicts are stable.

Do not jump directly from clean authored fixtures to broad geometry inference. First make known
claims measurable, explainable, and honestly verdicted.

## 9. Next Three Slices

1. **Adopt kernel report internally where relationship evidence is discussed.**
   Keep it internal unless a real caller needs a public surface. Use it to prevent old language
   from implying that authored claims or marker hints prove contact.

2. **Move profile obligations into data.**
   Add profile fields that say which evidence strengths/methods are expected for relationships
   such as `supports`, `connects`, `penetrates`, and `hosted_by`. This should remain vocabulary
   and obligation metadata, not proof.

3. **Audit containment refinement.**
   Reframe containment refinement outputs as observations, claims, evidence, and verdicts. Remove
   or isolate any private verdict vocabulary that would compete with the shared spine.

## 10. Historical Docs

The dated docs remain important because they explain how we got here:

- `2026-06-13-spatial-intelligence-foundation.md` records the OCCT/Topologic grounding work and
  the discipline of evidence gates.
- `2026-06-14-spatial-graph-projection-design.md` records the topology-projection insight and
  graph-policy framing.
- `2026-06-28-spatial-relationship-kernel-consolidation-v1-design.md` records the slice that
  corrected the relationship model into claim/evidence/verdict terms.

Use this document as the current synthesis. Use the dated docs as evidence, history, and deeper
context.
