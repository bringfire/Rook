# Proto-Skills

A staging ground for **emergent techniques** discovered during real Rook work
that aren't yet formal `/skills` but are worth capturing for reuse.

## What lives here

Each file is a single technique:

- **Trigger** — when to reach for this
- **Workflow** — the steps, in order, with the actual scripts
- **Design notes** — why each rule, what the tradeoffs are
- **First-use evidence** — concrete output from the session that birthed it

## Promotion path

A proto-skill graduates to `.claude/skills/<name>/SKILL.md` once:

1. It has been used **at least twice** on different geometry / contexts
2. The trigger phrases are stable
3. The script blocks have been parameterized (no hard-coded layer paths, etc.)
4. There's a small validation example

Until then, treat these docs as **recipes you read and adapt**, not as
automation. They live in `docs/rook_docs/` so they're searchable, but they're
explicitly *not* under `.claude/skills/` to keep the skill loader free of
half-baked entries.

## Index

| File | Technique | First used |
|---|---|---|
| [`revit-polysurface-classification.md`](./revit-polysurface-classification.md) | Split disjoint Revit-exported Brep, profile pieces, classify into similarity layers by topological signature | 2026-05-12, Crystal Bridges roof parts (241 pieces) |
| [`revit-family-fingerprinting.md`](./revit-family-fingerprinting.md) | Given a known-good exemplar, find all instances of the same Revit family in the document by thickness-invariant fingerprint matching. Handles intact, almost-correct, and exploded fragments. Layers on top of the topological classification above. | 2026-05-12, Crystal Bridges roof arched ribs (62 family instances found) |

## Composition: how these two techniques chain

```
[Dirty Revit polysurface]
        |
        v
[1. revit-polysurface-classification]
   Topological buckets:
     - 01_Panels_Flat
     - 02_Trim_Linear
     - 03_Profiled_Open
     - 04_Solids_Closed
     - 05_Artifacts_Tiny
        |
        v
[2. revit-family-fingerprinting]   <-- user picks an exemplar, finds its family
   Semantic buckets:
     - Family_X (across topological layers)
     - Family_Y
     - ...
```

The two techniques classify on **orthogonal axes**:

- **Topological** asks: "What kind of shape is this piece?" (closed solid vs. linear vs. panel vs. profiled vs. artifact)
- **Family fingerprint** asks: "What Revit family type is this an instance of?" (Plate-Spec-A vs. Plate-Spec-B vs. ...)

One Revit family can have instances scattered across multiple topological layers
(some intact = closed-solid, some broken = open-trim). Run the topological pass
first to clean up the geometry, then run family fingerprinting to recover
semantic identity.
