# Architectural Relationship Fixture

Small authored architecture-flavored fixture for relationship fact projection.

This fixture proves the existing neutral `RelationshipFact` substrate works beyond the Pearson
robot graph without adding ontology integration or geometry inference.

## Scope

- graph source: `architectural_relationship_fixture`
- graph revision: `a001`
- pose: `architectural_reference`
- owners: 7
- features: 10
- relationships: 5

Relationships:

```text
column_01.top_point supports slab_01.underside_region
door_01.body hosted_by wall_01.host_region
opening_01.profile voids wall_01.opening_region
duct_01.centerline penetrates wall_01.penetration_region
space_01.boundary bounded_by wall_01.inner_face
```

The wall is the main stress object. Its semantic context card should contain four incoming groups:

```text
hosted_by:incoming:accepted:authored_architectural_fixture
voids:incoming:accepted:authored_architectural_fixture
penetrates:incoming:accepted:authored_architectural_fixture
bounded_by:incoming:accepted:authored_architectural_fixture
```

## Authored Graph Schema

The persisted fixture graph and emitted Rhino user text use authored graph schema v2. Owner
records use `rook.graph.visual_type=object`, `rook.graph.object_id`, and
`rook.graph.object_kind`. Feature records use `rook.graph.owner_id`; `rook.graph.owner_kind` is
denormalized metadata that should match the resolved owner object's `object_kind`.

## Commands

Non-live:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Live, in a throwaway Rhino document:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_architectural_relationship_fixture_live.py -q
```
