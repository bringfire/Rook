# Pearson Robot Skeleton Graph Iterations

## g001 - Rest and reclined assembly graph

Status: generated and reviewed

Intent:
- Define a neutral graph vocabulary with nodes, members, poses, and symmetry pairs.
- Generate Rhino joint/member geometry directly from `assembly_graph.json`.
- Compare the rest T-pose and reclined robot pose in the same clean document.

Evaluation questions:
- Does the rest pose read as a sane identity graph?
- Does the reclined pose read as the beginning of the chair-like robot posture?
- Does Rook's observed scene graph provide useful feedback on member connectivity?
- What semantic graph concepts are missing from the existing architectural relationship scene graph?

Rhino generation result:
- Generated 58 graph visualization objects: 30 joint spheres and 28 member curves.
- Saved the named view `skeleton_graph_overview`.
- Captured two evidence screenshots:
  - `screenshots/g001_skeleton_graph_plain.png`
  - `screenshots/g001_skeleton_graph_overview.png`

Observed scene graph result:
- Rook reported 58 nodes, 192 edges, and 24 connected components.
- Relationship distribution: 158 `near`, 16 `above`, 12 `intersects`, and 6 `adjacent`.
- Shape classifications are driven by generated geometry, not graph semantics: joint spheres read as compact `block` objects, while line members classify as `panel`, `bar`, `post`, or `slab` depending on their bounding boxes.

Evaluation:
- The graph-derived visual representation works: changing graph node coordinates or member endpoints will directly change the Rhino skeleton.
- The rest pose is useful as an identity/T-pose graph for checking symmetry, sidedness, and proportions.
- The reclined pose is useful as a first chair-like posture, but it is still diagrammatic. It does not yet encode contact/support intent, seat depth, arm-rest height, or the blocky mass relationships visible in the reference robot.
- Rook's architectural scene graph does not yet understand authored node-member incidence. It sees proximity between generated objects, but not the explicit graph fact that a member connects two named joints.

Likely g002 direction:
- Keep `node`, `member`, and `pose` as the formal vocabulary.
- Add explicit graph-derived relationship projection so scenegraph queries can answer "which members connect to this node?" without relying on spatial `near` inference.
- Consider generating members as thin pipes/cylinders that physically penetrate the joint spheres, so the spatial scene graph also has stronger contact evidence.
- Add pose intent metadata such as `support`, `contact_candidate`, `seat_plane`, and `load_path` once the bare topology remains visually sane.

## g002 - Feature-level authored relationships

Status: generated and reviewed

Intent:
- Keep the same robot topology and poses as `g001`.
- Upgrade the schema from a simple node/member graph to a feature graph:
  - nodes own point features;
  - members own endpoint features;
  - authored `connects` relationships bind member endpoints to node points.
- Keep the vocabulary neutral enough to later describe architectural cases such as column-to-slab point/area support and wall-to-slab line/area support.

Schema result:
- `assembly_graph.json` revision is now `g002`.
- Counts: 15 nodes, 14 members, 43 features, and 28 authored relationships.
- Every authored relationship has:
  - `type`: currently `connects`;
  - `from` / `to`: feature ids, not raw object ids;
  - `contact_kind`: currently `point_to_point`;
  - `provenance`: `authored_assembly_graph`.

Rhino generation result:
- Generated 200 tagged graph visualization objects across the two poses:
  - 30 joint objects;
  - 28 member objects;
  - 86 feature marker objects;
  - 56 relationship marker objects.
- Saved evidence screenshot:
  - `screenshots/g002_feature_graph_plain.png`
- Feature and relationship markers are lifted `0.08m` above their authored positions for readability. The user strings preserve both authored feature positions and debug marker positions.

Metadata spot check:
- Sample relationship object:
  `relationship_reclined_robot_spine_base_to_spine_top.start_connects_spine_base`
- Authored relationship:
  - `rook.graph.relationship_type`: `connects`
  - `rook.graph.from_feature`: `spine_base_to_spine_top.start`
  - `rook.graph.to_feature`: `spine_base.point`
  - `rook.graph.contact_kind`: `point_to_point`
  - `rook.graph.from_feature_position_m`: `[0.0,-0.22,0.78]`
  - `rook.graph.to_feature_position_m`: `[0.0,-0.22,0.78]`
- Display-only marker data is separate:
  - `rook.graph.marker_start_m`
  - `rook.graph.marker_end_m`
  - `rook.graph.visual_lift_m`

Observed scene graph result:
- The current Rhino document's generic scene graph reported 501 nodes and 6,239 inferred edges after this run.
- That document-level total includes objects outside the current tagged `pearson_robot_skeleton_graph` subset. The generator only clears and replaces objects with `rook.graph.source == pearson_robot_skeleton_graph`.
- The generic scene graph remains noisy for this purpose because it sees all feature markers and debug ticks as spatial objects. This is expected and reinforces that authored feature relationships need a semantic projection path rather than more proximity inference.

Evaluation:
- The feature graph approach is better than `g001` for Rook-native modeling. It separates elements, features/ports, and relationships in a way that can generalize beyond robot skeletons.
- The visual layer now shows where authored topology lives without pretending generic spatial inference has understood it.
- The next useful step is not more marker geometry. It is a read-model projection that turns relationship user strings into semantic graph edges such as `authored_connects`, scoped by provenance and graph revision.
- After that, architecture cases can use the same schema shape with new feature kinds (`surface`, `edge`, `region`) and contact kinds (`point_to_area`, `line_to_area`, `surface_to_surface`).
