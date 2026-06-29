# Pearson Robot Skeleton Graph Experiment

This experiment tests a graph-first reconstruction workflow for the Pearson robot.
The graph is the source of truth; Rhino geometry is only a generated visual/debug
view of graph nodes, members, features, relationships, and poses.

## Workflow

1. Edit `assembly_graph.json`.
2. Generate the Rhino visualization script:
   `python experiments\pearson_robot_skeleton_graph\scripts\build_skeleton_graph_rhino.py experiments\pearson_robot_skeleton_graph\assembly_graph.json experiments\pearson_robot_skeleton_graph\generated\skeleton_graph_rhino.py`
3. Execute the generated script in Rhino through Rook `rhino_execute`.
4. Inspect the generated node spheres, member curves, feature markers, and relationship
   markers with Rook's scene graph tools.

## Language

Use neutral graph language in the source data:

- `node`: a named point/frame in the assembly graph.
- `member`: a directed graph edge connecting two nodes.
- `feature`: a named port, point, edge, surface, or region owned by an element.
- `relationship`: an authored semantic connection between features.
- `pose`: a named spatial state of the same topology.

Domain metaphors like `bone`, `spine`, `rib`, or `datum` may appear as aliases,
but they are not the primary schema terms.

## Display Convention

Feature and relationship markers are debug geometry. In `g002`, they are lifted slightly
above their authored positions so they can be seen in Rhino. Object user strings preserve
the authored feature positions separately from marker positions.
