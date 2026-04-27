# Public-Facing Skills Brainstorm

**Date:** 2026-04-10
**Goal:** Expand the skill library for public Rook users shipping with v1.

---

## Current Skill Inventory (14 skills)

### Pipelines
- `/design-grasshopper` → `/plan-grasshopper` → `/execute-grasshopper` — full GH definition design pipeline
- `/design-road` → `/masterplan-roads` — road network design pipeline

### One-Shot Creators
- `/twisted-column` — parametric twisted architectural columns
- `/chirp` — single LLM-powered GH component
- `/chirp-cascade` — multi-component reasoning cascades

### Onboarding
- `/project-setup` — configure a project folder for Rook (CLAUDE.md generation + interview)

### Dev / Maintenance
- `/build-release` — full plugin suite build + installer
- `/consolidate` — DSPy knowledge consolidation
- `/test` — layered test runner
- `/validate-security` — security hardening validation

---

## Candidate Categories

### A. Architectural Primitives (one-shot creators)
Expand on the `/twisted-column` format — guided single-shot geometry creators.

| Skill | Description |
|-------|-------------|
| `/parametric-stair` | Straight, spiral, switchback stairs with parametric treads/risers |
| `/parametric-roof` | Gable, hip, mansard, shed, butterfly roof forms |
| `/facade-pattern` | Paneling with attractor-based variation, fenestration patterns |
| `/parametric-truss` | Pratt, Warren, Howe trusses from span + depth |
| `/dome` | Geodesic, ribbed, parametric dome forms |
| `/folded-plate` | Origami-style folded plate structures |
| `/voronoi-panels` | Voronoi tessellation on surfaces or volumes |
| `/space-frame` | 3D lattice / space frame structures |
| `/curtain-wall` | Mullion grid with parametric panel types |
| `/waffle-structure` | Interlocking slotted ribs from a surface |

**Why this category:** "Wow, look what it just made" demos that travel well on social media. `/twisted-column` already proves the format works. Each one is self-contained, low-risk, and showcases the knowledge store + intent runtime.

### B. Cleanup / File Hygiene (convention-driven)

Every Rhino user deals with messy files. These are "actually useful on day one" skills.

**The problem:** Skills like `/clean-layers` are inherently opinionated — "clean"
means different things to different firms, projects, and users. Hard-coding opinions
makes skills brittle and argumentative. A skill that reorganizes layers according to
its own idea of "correct" is more likely to destroy someone's workflow than improve it.

**The solution: convention-driven skills.** Separate the *engine* (what the skill
does) from the *policy* (what "correct" means). A shared convention system defines
the target state; individual skills audit against it and propose changes.

#### Convention System (prerequisite for all Category B skills)

```
.rook/conventions.yaml        ← project-level convention file
  layers:                     ← layer tree, colors, linetypes, visibility defaults
  naming:                     ← regex/prefix rules for objects, blocks, materials
  materials:                  ← material-to-layer assignments
  blocks:                     ← naming scheme, nesting expectations
  tolerances:                 ← units, abs/rel tolerance, mesh density thresholds
  metadata:                   ← user-string key-value conventions
```

Human-readable YAML so users can hand-edit. Portable across projects (copy or
symlink for firm-wide standards). Different projects can have different conventions.

#### Convention lifecycle

| Skill | Description |
|-------|-------------|
| `/capture-convention` | Analyze a reference .3dm file and extract conventions to `.rook/conventions.yaml`. Captures layer tree, naming patterns, materials, tolerances, block organization. The "golden file" approach — show me what correct looks like, and I'll remember. |
| `/apply-convention` | Compare current file against `.rook/conventions.yaml`. Audit → propose → apply. Shows every discrepancy, lets user approve/reject individual changes. Never destructive without consent. |

#### Convention-aware cleanup skills

All Category B skills follow the same pattern:
1. Check for `.rook/conventions.yaml` — if present, use it as the definition of "correct"
2. If absent, offer to run `/capture-convention` first, or interview for ad-hoc preferences
3. **Audit → Propose → Apply** — always show what would change, let user approve per-change

| Skill | Description |
|-------|-------------|
| `/clean-layers` | Compare layer structure against convention. Propose: add missing standard layers, fix colors/linetypes, flag orphan layers (empty + not in convention). Never deletes without approval. |
| `/audit-blocks` | Find broken, unused, or duplicate block definitions; report against naming conventions; optional fix |
| `/purge-file` | Remove unused materials, layers, blocks, hatches, linetypes — but respects convention-defined "keep even if empty" layers |
| `/import-cad-cleanup` | Map imported DWG layers to convention layer tree, explode nested blocks, normalize names. Convention file defines the DWG→Rhino layer mapping. |
| `/fix-meshes` | Find and repair non-manifold, degenerate, or naked-edge meshes using tolerance thresholds from convention |
| `/check-units` | Validate document units and tolerances against convention; offer conversion |

#### Integration with `/project-setup`

The existing Q5 ("Any conventions?") extends naturally:

> "Do you have a reference .3dm file with your standard layer structure?
> I can extract your conventions so cleanup skills know what 'correct'
> looks like for this project."
>
> - Yes → runs `/capture-convention` → saves `.rook/conventions.yaml`
> - No → skip (skills will interview individually or propose defaults)
> - Use conventions from another project → copies `.rook/conventions.yaml`

#### Why this architecture

- **No opinions baked into skills.** The skill is the engine; the convention file is the policy.
- **Reusable across projects.** A firm defines conventions once, applies everywhere.
- **Shareable.** Convention files can be checked into git, shared with collaborators, published as community templates.
- **Graceful degradation.** No convention file? Skills still work — they interview or propose conservative defaults.
- **One mechanism for all skills.** Solves the "opinionated" problem once rather than per-skill.

**Implementation order:** `/capture-convention` first (the foundation), then `/clean-layers` (first consumer, proves the pattern), then remaining skills adopt the same convention-aware pattern.

### C. Interop / Exports
Getting geometry out of Rhino cleanly is a constant struggle.

| Skill | Description |
|-------|-------------|
| `/export-revit` | Clean export for Revit (layer mapping, units, block → family conversion) |
| `/export-unreal` | Datasmith-friendly export with material mapping |
| `/export-gltf` | Web-viewer-ready export with mesh optimization |
| `/export-blender` | Clean FBX/USD with material + UV preservation |
| `/export-laser` | Flatten and nest geometry for laser cutting |

**Why this category:** Everyone needs export. But high-effort per format, moderate novelty. Consider deferring.

### D. Documentation / Drawings
Sheet setup and 2D output from 3D models.

| Skill | Description |
|-------|-------------|
| `/setup-sheets` | Create Rhino layouts with title block, scaled viewports, annotation |
| `/auto-dimension` | Automatically dimension a 2D drawing or layout |
| `/make-2d` | Generate 2D line drawings from 3D model (plan, section, elevation) |
| `/section-cut` | Interactive section plane → clean 2D output with hatching |

**Why this category:** Real workflow need, but Rhino's layout system is finicky. May be fragile as a v1 skill.

### E. Read-the-Canvas / Debugging (knowledge store differentiator)
Hardest for competitors to copy because it depends on Rook's knowledge store.

| Skill | Description |
|-------|-------------|
| `/explain-definition` | Read a GH definition and describe what it does in plain language |
| `/debug-definition` | Analyze why a GH definition isn't producing expected output |
| `/find-component` | "I need something that does X" → knowledge store search → recommendation |
| `/explain-error` | Diagnose Rhino/GH error messages with context-aware suggestions |
| `/audit-definition` | Check a GH def for performance issues, deprecated components, bad patterns |

**Why this category:** Direct expression of the positioning thesis — Rook knows Grasshopper better than any other tool. This is the moat. Hard to replicate without 1,230 knowledge notes + sparse index.

### F. Vision / Image-to-CAD (strategic, deferred)
Per ArchSynth competitive strategy. Dependent on HAWPv3 spike resolution.

| Skill | Description |
|-------|-------------|
| `/photo-to-cad` | Extract line drawings from photos → clean CAD geometry |
| `/sketch-to-3d` | Interpret hand sketches → 3D model |
| `/reference-board` | Set up image reference grid in Rhino viewport |

**Why this category:** Strategic differentiator, but HAWPv3 spike not resolved. Defer to post-v1.

### G. Learning / Knowledge Meta
Let users interact with the knowledge system directly.

| Skill | Description |
|-------|-------------|
| `/teach-me` | Interactive tutorial on a Rhino/GH topic, adapted to user level |
| `/learn-pattern` | Record a successful workflow as a reusable knowledge pattern |

**Why this category:** Retention. Lets users grow with the tool rather than hitting a ceiling.

### H. Onboarding (first-run experience)
Bridge the gap between install and productive use.

| Skill | Description |
|-------|-------------|
| `/project-setup` | Configure project folder — CLAUDE.md generation, interview, conventions |
| `/what-can-you-do` | Guided discovery of Rook's capabilities with live demos |
| `/quick-tour` | 5-minute hands-on walkthrough: create geometry, build a GH def, query knowledge |

**Why this category:** First impression. Users who don't get value in the first 10 minutes don't come back. `/project-setup` is the mechanical prerequisite; `/what-can-you-do` and `/quick-tour` are the emotional hook.

---

## Infrastructure: Script Library

Skills and agents need scripts that run inside Rhino's Python/C# environment.
Today every script is generated ad-hoc by the LLM — non-deterministic, slow,
untested, duplicated. A shared script library fixes this, but not in the way
a traditional utility library works.

### The key insight

Scripts exist on a spectrum:

**Run as-is (deterministic utilities).** Pure data extraction or boolean checks.
No context sensitivity — same API calls every time, any file.

| Script | Purpose |
|--------|---------|
| `extract_layers.py` | Dump layer tree to structured JSON |
| `extract_materials.py` | Enumerate materials + layer assignments |
| `extract_blocks.py` | List block definitions, instance counts, nesting |
| `extract_tolerances.py` | Read document units, abs/rel tolerance |
| `find_mesh_issues.py` | Find naked edges, non-manifold, degenerate faces |
| `document_summary.py` | Object counts by type, layer stats, file metadata |

These can be run directly by the user (`RunPythonScript` in Rhino) or by the
agent via `rhino_execute`. No LLM involvement needed at runtime.

**Adapt then run (reference patterns).** Mutation scripts that need to know about
*this specific file and user*. The script provides the structural skeleton and
domain knowledge (which API calls, what order, what edge cases). The LLM provides
the situational adaptation.

| Script | Purpose | What gets adapted |
|--------|---------|-------------------|
| `clean_layers.py` | Restructure layers to match a target | Target tree, merge rules, keep-list |
| `map_dwg_layers.py` | Map imported DWG layers to convention | Source→target mapping table |
| `organize_blocks.py` | Rename/restructure block definitions | Naming scheme, nesting rules |
| `apply_materials.py` | Assign materials per layer convention | Material→layer mapping |
| `batch_export.py` | Export objects by layer/group/name | Formats, naming, mesh settings |

The LLM's value here is **minimal, precise adaptation** — not generating the script
from scratch, and not running it blindly hoping it works. The workflow is:

1. **Assess context** — what does this file look like, what's unusual
2. **Find best-fit script** — the reference implementation closest to the need
3. **Adapt minimally** — modify only what the context requires (a mapping table,
   a threshold, a filter condition)
4. **Execute** — send the adapted version via `rhino_execute`

### Writing scripts for this model

Scripts are written for **Claude as the primary reader**, not just the Python
interpreter. This means:

- **Clear variable names** — `target_layer_tree` not `tlt`
- **Comments on the "why" at decision points** — so Claude knows what's safe to
  change vs. what's load-bearing
- **Modular structure** — functions that can be swapped individually without
  rewriting the whole script
- **Marked adaptation points** — comments like `# ADAPT: change this mapping for
  your layer convention` so Claude knows where to focus
- **Structured output** — always return JSON so the agent can parse results

### Where it lives

```
scripts/
├── rhino/                    ← run inside Rhino's Python environment
│   ├── extract_layers.py     ← [run-as-is] layer tree → JSON
│   ├── extract_materials.py  ← [run-as-is] materials → JSON
│   ├── extract_blocks.py     ← [run-as-is] block defs → JSON
│   ├── extract_tolerances.py ← [run-as-is] units/tolerance → JSON
│   ├── find_mesh_issues.py   ← [run-as-is] mesh diagnostics → JSON
│   ├── document_summary.py   ← [run-as-is] full file summary → JSON
│   ├── clean_layers.py       ← [adapt] restructure layers
│   ├── map_dwg_layers.py     ← [adapt] DWG import layer mapping
│   └── ...
├── gh/                       ← run inside Grasshopper's Python environment
│   └── ...
└── lib/                      ← shared helpers imported by the above
    └── ...
```

Each script has a header comment block:

```python
# --- Script metadata ---
# name: extract_layers
# type: run-as-is | adapt
# domain: rhino
# purpose: Walk the Rhino document layer tree and output structured JSON
# used-by: /capture-convention, /clean-layers, /purge-file
# output: JSON to stdout
# adapt-points: none (run-as-is)
```

### How skills reference scripts

Skills point Claude at the right script:

```markdown
### Step 2: Extract layer tree
Read `scripts/rhino/extract_layers.py` and send it via `rhino_execute`.
Parse the JSON output.
```

For adapt-type scripts:

```markdown
### Step 3: Apply layer cleanup
Read `scripts/rhino/clean_layers.py`. This is an adapt-type script.
Review the current layer structure (from Step 2) and the convention
file. Adapt the TARGET_LAYERS mapping and the MERGE_RULES at the
marked adaptation points, then send via `rhino_execute`.
```

### Deployment

Ships with the installer alongside knowledge stores. The installer already
deploys `scripts/session-start.sh` — extend to include `scripts/rhino/` and
`scripts/gh/`. Small files, high value.

Users can also run the `run-as-is` scripts directly in Rhino via
`RunPythonScript` — no agent involvement needed. This makes the scripts
independently useful even outside the AI workflow.

---

## Recommendation: First Wave (v1 Launch)

**Priority categories: H (Onboarding) + A (Primitives) + E (Explain/Debug) + B (Cleanup)**

### Rationale
- **H** — without onboarding, nothing else matters; `/project-setup` already shipped
- **A** — demo-ready, shareable, proves the "AI builds geometry" promise
- **E** — the moat; no competitor has this depth of GH knowledge
- **B** — immediate practical value; builds trust that Rook is useful, not just flashy

### Defer
- **C (Exports)** — high effort per format, moderate novelty
- **D (Docs/Drawings)** — Rhino layout system is fragile, risky for v1
- **F (Vision)** — blocked on HAWPv3 spike
- **G (Learning meta)** — nice-to-have, not launch-critical

---

## Implementation Tracker

### Shipped
| Skill | Category | PR | Date |
|-------|----------|----|------|
| `/project-setup` | H. Onboarding | [#7](https://github.com/bringfire/Rook/pull/7) | 2026-04-12 |

### Next up — Infrastructure + Convention system
| Item | Type | Status | Depends on | Notes |
|------|------|--------|------------|-------|
| Script library scaffolding | Infrastructure | Not started | — | `scripts/rhino/` directory, header format, installer deployment |
| `extract_layers.py` | Script (run-as-is) | Not started | scaffolding | First script. Used by `/capture-convention` and `/clean-layers` |
| `extract_materials.py` | Script (run-as-is) | Not started | scaffolding | |
| `extract_blocks.py` | Script (run-as-is) | Not started | scaffolding | |
| `extract_tolerances.py` | Script (run-as-is) | Not started | scaffolding | |
| `document_summary.py` | Script (run-as-is) | Not started | scaffolding | |
| `find_mesh_issues.py` | Script (run-as-is) | Not started | scaffolding | |
| `/capture-convention` | Skill | Not started | extraction scripts | Runs extraction scripts → assembles `.rook/conventions.yaml` |
| `clean_layers.py` | Script (adapt) | Not started | `extract_layers.py` | Reference pattern for layer restructuring |
| `/clean-layers` | Skill | Not started | `/capture-convention` + `clean_layers.py` | First convention-aware consumer. Proves the full pattern. |

### First wave — no convention dependency
| Skill | Category | Status | Notes |
|-------|----------|--------|-------|
| `/what-can-you-do` | H. Onboarding | Not started | Guided capability discovery |
| `/quick-tour` | H. Onboarding | Not started | Hands-on 5-min walkthrough |
| `/parametric-stair` | A. Primitives | Not started | High demo value |
| `/parametric-roof` | A. Primitives | Not started | |
| `/facade-pattern` | A. Primitives | Not started | |
| `/explain-definition` | E. Explain/Debug | Not started | Knowledge store moat |
| `/debug-definition` | E. Explain/Debug | Not started | Knowledge store moat |
| `/find-component` | E. Explain/Debug | Not started | Knowledge store moat |

### After convention system ships
| Skill | Category | Status | Notes |
|-------|----------|--------|-------|
| `/apply-convention` | B. Conventions | Not started | Audit → propose → apply against conventions |
| `/purge-file` | B. Cleanup | Not started | Convention-aware |
| `/fix-meshes` | B. Cleanup | Not started | Convention-aware (tolerance thresholds) |
| `/audit-blocks` | B. Cleanup | Not started | Convention-aware (naming rules) |
| `/import-cad-cleanup` | B. Cleanup | Not started | Convention-aware (DWG→Rhino layer mapping) |
| `/check-units` | B. Cleanup | Not started | Convention-aware (tolerance validation) |

*Update this table as skills are implemented. Full candidate list in category sections above.*

---

## Open Questions

1. How many skills per category for v1? (3-5 each? Or go deep on one category?)
2. Should primitives be single-shot (like `/twisted-column`) or guided pipelines (like `/design-grasshopper`)?
3. Which specific primitives would make the best launch demos?
4. Should `/quick-tour` be a skill or built into the `/project-setup` post-setup flow?
5. How do we test skills without live Rhino in CI? (Layer 3/4 test concern)
6. Convention file scope: should `.rook/conventions.yaml` support partial overrides (project inherits from firm-wide base + overrides specific keys)? Or keep it flat for v1?
7. Should `/capture-convention` also capture from a `.dwg` or `.3dm` template file, or only from a fully-built reference file?
8. Community convention templates: should we ship a few starter templates (e.g., "AEC standard", "product design", "fabrication")? Or let conventions be entirely user-defined at launch?
9. Script library: should adapt-type scripts use a formal marker syntax (`# ADAPT:`) or is free-form commenting sufficient for Claude to identify adaptation points?
10. Should run-as-is scripts be exposed as MCP tools (e.g., `run_library_script(name="extract_layers")`) or is read-then-send via `rhino_execute` sufficient for v1?
