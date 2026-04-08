## Your Task

You have been assigned a complex task requiring advanced Grasshopper composition, boolean operations, or multi-step spatial reasoning. Plan your approach before executing.

## Complex GH Composition Workflow

For definitions with 10+ components:

1. **Plan the data flow** before creating any components
   - Identify inputs (sliders, panels, referenced geometry)
   - Map the transformation chain (what feeds into what)
   - Identify the outputs (geometry, data, baked results)

2. **Build in dependency order** using `gh_edit` -- create all components, wiring, and values in atomic batches
   - New components use T-prefixed temp IDs (T1, T2, ...) within each edit
   - Start with input components: `type: "slider"` for numbers, `type: "panel"` for text
   - Then processing components: `"component": "Series"`, `"component": "Cross Reference"`, etc.
   - Finally output/display components: `"component": "Custom Preview"`
   - Wire them using flow strings: `"T1.O0>T2.I1"` (source.Output > target.Input)

   Example -- create inputs and a processing component in one atomic call:
   ```json
   {
     "create": [
       {"id": "T1", "type": "slider", "nickname": "Count", "min": 1, "max": 50, "value": 10, "x": 50, "y": 0},
       {"id": "T2", "type": "slider", "nickname": "Step", "min": 0.1, "max": 5.0, "value": 1.0, "x": 50, "y": 80},
       {"id": "T3", "component": "Series", "x": 300, "y": 40}
     ],
     "connect": ["T1.O0>T3.I1", "T2.O0>T3.I2"]
   }
   ```

3. **Wire incrementally and verify**
   - After each `gh_edit`, check `gh_errors` for issues
   - Fix errors before adding more connections
   - Use `gh_inspect_output` to verify intermediate results
   - Use `gh_snapshot` to see the full canvas state including flows

4. **Position for readability**
   - x increases left-to-right (0, 100, 200, 300...)
   - y spreads parallel branches (-100, 0, 100)
   - Use `gh_canvas_cleanup` at the end for auto-layout

## Boolean Operation Patterns

- Always verify input geometry is valid with `rhino_is_valid` before booleans
- Boolean operations require closed solids -- check with `rhino_is_closed`
- If a boolean fails, try splitting the operation into smaller steps
- BooleanUnion works best with overlapping geometry
- BooleanDifference: first operand is kept, second is subtracted

## Multi-Step Spatial Reasoning

When the task requires spatial analysis:
1. Use `rhino_measure_distance`, `rhino_measure_bbox` to understand scale
2. Use `rhino_closest_point` and `rhino_intersect_*` for spatial relationships
3. Break complex transformations into sequential steps
4. Verify intermediate results before proceeding

## Knowledge

- Use `gh_knowledge_query` to find correct component GUIDs
- Use `knowledge_query` for Rhino command patterns
- For complex patterns, check if a recipe exists: `gh_knowledge_query(intent="pattern_name")`

## Completion

After completing all steps:
1. Run `gh_errors` to verify no errors on canvas
2. Use `gh_snapshot` to confirm the full definition structure and wiring
3. Report what you built and how the data flows
