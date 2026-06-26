# Relationship Fact Projection Smoke

Small live-validation fixture for `scene_project_relationship_facts`.

This smoke fixture avoids the full Pearson robot document. Each run clears the dedicated
`Rook_RelationshipFactSmoke` layer, then creates exactly five Rhino objects:

- one member owner curve;
- one joint owner point;
- two feature marker points;
- one relationship marker curve.

All five objects are stamped with:

```text
rook.graph.source = relationship_fact_smoke
rook.graph.revision = smoke001
rook.graph.pose = smoke_pose
```

The script output includes `clearedObjectCount`, so repeated runs in the same document should
still leave exactly the five current fixture objects on the smoke layer.

Expected projection:

```text
scene_project_relationship_facts(graph_source="relationship_fact_smoke")
```

Expected response:

```json
{
  "success": true,
  "projectionKind": "relationship_fact_v1",
  "counts": {
    "relationshipFactCount": 1,
    "projectedEdgeCount": 1,
    "skippedFactCount": 0
  },
  "byRelationshipType": {
    "connects": 1
  },
  "byPose": {
    "smoke_pose": 1
  }
}
```

Then inspect the two owner object ids with:

```text
scene_context(object_ids=["<member object id>", "<joint object id>"], sync=false)
```

Expected context includes:

```text
connects: ... via smoke_member.start -> smoke_joint.point, point_to_point, accepted, authored_assembly_graph
connected by: ... via smoke_member.start -> smoke_joint.point, point_to_point, accepted, authored_assembly_graph
```
