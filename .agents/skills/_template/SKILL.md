---
name: your-skill-name
description: |
  Brief description of what this skill does.
  Include trigger phrases: "when user mentions X, Y, or Z".
  Be specific about the design pattern or workflow this enables.
---

# Skill Name

Brief overview of the workflow this skill enables.

## Prerequisites

- List any geometry that must exist before starting
- Note any layer setup requirements
- Specify unit assumptions if relevant

## Workflow Steps

### Step 1: [Name]

**Intent:** Describe what this step accomplishes

```python
circle = rhino_create(type="CIRCLE", center=[0, 0, 0], radius=5)
circle_id = circle["id"]
rhino_geometry(id=circle_id)
```

**Notes:**
- Any gotchas or tips for this step

### Step 2: [Name]

**Intent:** Describe what this step accomplishes

```python
extrusion = rhino_extrude(
    curveId=circle_id,
    direction=[0, 0, 10],
    cap=True,
)
rhino_geometry(id=extrusion["id"])  # verify geometry and solid state
```

### Step 3: [Continue as needed...]

## Parameters to Expose

For session export, these parameters should be adjustable:
- `parameter_name`: Description (default: value)
- `another_param`: Description (default: value)

## Gotchas

- Document any non-obvious behaviors
- Selection workflow requirements
- Order dependencies

## References

- See [gotchas.md](./references/gotchas.md) for detailed command gotchas
- See [variations.md](./references/variations.md) for alternative approaches

## Example Output

Describe what the final geometry looks like when the workflow completes successfully.
