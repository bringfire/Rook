# Rook × Gemma Challenge Strategy (May 2026)

## Purpose

This document captures the strategy discussion for entering the DEV Gemma challenge with a submission that:

1. Shows **Rook as the primary system** (real CAD/GH execution substrate), and
2. Shows **Gemma as the local cognitive core** (multi-model orchestration), while
3. Optionally using Gemini family media models (including Nano Banana when available in catalog) as a finishing lane.

It is intentionally grounded in the current repository architecture and implementation seams.

---

## 1) Contest Understanding and Submission Mechanics

- The challenge expects a **post published on DEV** (dev.to challenge submission), not only social posting.
- Practical strategy: publish one strong build-track post first, then optionally a second writing-track post derived from the same implementation work.
- Timeline context discussed:
  - Challenge start: 2026-05-06
  - Submission deadline: 2026-05-24 (11:59 PM PDT)
  - Winners announced: 2026-06-04

> Note: dates above came from challenge page review during planning; verify one final time immediately before submission.

---

## 2) Architectural Positioning: What We Already Have

### 2.1 Runtime architecture to emphasize publicly

Rook already has a production-shaped runtime:

- Python MCP server + chat service
- Native C++ Rhino plugin as sole public HTTP surface
- Internal managed companion for GH callback bridge and selected route exceptions

Key architecture claims we can responsibly make:

- Native plugin is the only public Rhino HTTP surface.
- System has broad route coverage (hundreds of routes) and a typed intent/runtime pipeline.
- Agentic orchestration is already present (planner/worker/guardian patterns).

### 2.2 Existing reliability and execution posture

The chat/execution policy already encodes substrate preference:

1. Structured native tools first
2. Intent orchestration second
3. Command scripting fallback
4. Raw script fallback last

This is a major competition differentiator versus generic chatbot demos: we can demonstrate verified, stateful geometric operations with recovery paths.

### 2.3 Existing model orchestration primitives

Rook already supports role-based model allocation and profile switching:

- Roles: planner, worker, specialist, guardian, dspy
- Profiles: cloud, hybrid, local, lmstudio, finetuned
- Local provider support and detection (Ollama, LM Studio)
- `model_override` per conversation start in chat server
- DSPy teacher/student optimization configuration

This means we can present “multi-Gemma” orchestration without inventing new architecture.

---

## 3) Core Submission Narrative

## “Gemma Mesh for Design Execution”

**Narrative statement:**

Rook uses a mesh of Gemma-family local models, each assigned to a distinct workload role, then routes outputs through RookVision for cloud media realization when needed.

### Role mapping concept (implementation-friendly)

- **Gemma Fast / Small (local):** worker + guardian
  - intent normalization
  - fast iteration
  - loop/drift detection
- **Gemma Reasoning / Larger (local):** specialist
  - complex GH composition
  - multi-step geometric reasoning
  - conflict resolution
- **Gemma DSPy student/teacher pair (local or mixed):**
  - optimization and pattern consolidation for recurring workflows

Planner can remain cloud in first iteration if needed for reliability while still presenting a primarily local execution story.

---

## 4) Full-Featured Workflow Expression (Rook + Gemma + Vision + Chirp)

## “Local-to-Frontier Design Media Foundry”

### Phase A — Local design cognition

1. User provides a design brief and constraints.
2. Worker/specialist Gemma roles decompose and execute tasks.
3. Guardian model monitors trajectories (stuck loops, budget drift, retries).
4. Rook executes through native tools with explicit verification.

### Phase B — Chirp embedding in GH canvas

1. Use `chirp_create` to place intelligent GH script components.
2. Seed categories such as planner/interpreter/critic/narrator.
3. Keep reasoning and corrective loops embedded in the canvas logic.

### Phase C — RookVision output staging and media realization

1. Prepare curated artifacts from the geometry workflow.
2. In Vision, query model catalogs (image/video) and select available targets.
3. Use estimate route and async job routes for reproducible generation flow.
4. If Nano Banana appears in registered catalog, use it for fast concept variants; escalate selected outputs to richer Gemini image/video models.

### Why this wins

- Demonstrates a real end-to-end system, not a single prompt gimmick.
- Makes Gemma central to cognition and control loops.
- Showcases Rook’s architecture breadth (native execution, GH automation, vision dispatch, session/verification behavior).

---

## 5) Deliverable Scope (just ahead of current state)

### 5.1 What is already in place

- Model profile and role routing framework
- Conversation model override
- DSPy teacher/student plumbing
- Chirp component generation path
- Vision model listing / estimation / job surfaces

### 5.2 Minimal, high-impact additions for challenge

1. Add a challenge profile (e.g., `gemma_showcase`) in model profile data/config.
2. Add a simple orchestration preset for role mapping (worker/specialist/guardian/dspy).
3. Add a demo macro/workflow script for repeatable recording.
4. Add lightweight telemetry snapshot in demo run (latency/success/retry counts).
5. Prepare submission assets (diagram + 2–3 min demo walkthrough + metrics table).

### 5.3 Stretch additions (if schedule allows)

- Dynamic model handoff mid-turn/session for specialist bursts.
- Adaptive Chirp cascade templates for common design archetypes.
- Auto-storyboard export for vision generation sequence.

---

## 6) Evaluation Rubric for Internal Readiness

Before shipping submission, validate each axis:

### A. Technical quality

- End-to-end pipeline works on clean environment
- Deterministic failure handling and fallback behavior demonstrated
- No broken tool chain in recorded flow

### B. Intentional model usage

- Each Gemma role is justified by workload characteristics
- Role/model table appears in final post
- At least one measured tradeoff shown (speed vs reasoning depth)

### C. Originality

- Domain-specific design workflow (Rhino/GH) is core, not decorative
- Chirp + Vision integration is part of one coherent user journey

### D. User experience

- Clear before/after visuals
- Minimal operator friction
- Narrated decision checkpoints

### E. Evidence

- Include objective metrics from run:
  - success rate
  - retries/fallback usage
  - latency by phase
  - cost/usage proxy where available

---

## 7) Recommended Demo Script (2–3 minutes)

1. **Opening (15s):** “Rook runs local Gemma model mesh for design reasoning.”
2. **Brief ingestion (20s):** submit natural language design goal.
3. **Execution (45s):** show worker + specialist behavior with one visible correction.
4. **Chirp (30s):** inject one or two Chirp nodes and show generated component logic.
5. **Vision (35s):** list models, select available Gemini/Nano Banana entry, estimate, submit.
6. **Result and metrics (20s):** before/after + run stats + why model split mattered.

---

## 8) Submission Post Structure (DEV)

1. Problem statement (real design pain)
2. Why local-first reasoning matters in CAD workflows
3. Architecture overview (Rook substrate + Gemma roles + Vision lane)
4. Model-role mapping table
5. Implementation details and key routes/tools
6. Demo walkthrough
7. Metrics and learnings
8. Limitations and next steps
9. Link to repo/commit and reproducibility notes

---

## 9) Risk Register and Mitigations

### Risk: model naming/availability drift (Nano Banana/Gemini variants)
- Mitigation: discover models dynamically from runtime catalog at demo time; avoid hardcoding model IDs in narration.

### Risk: over-scoped implementation before deadline
- Mitigation: lock one flagship path (e.g., convention-aware cleanup + media realization) and defer extras.

### Risk: environment-specific plugin constraints
- Mitigation: perform final capture/testing in proper Windows + Rhino toolchain environment.

### Risk: generic AI demo perception
- Mitigation: keep Rook-native execution and GH integration as the backbone of the story.

---

## 10) Next Actions Checklist

- [ ] Define final flagship scenario (single coherent workflow)
- [ ] Lock model-role mapping for Gemma showcase
- [ ] Implement minimal additions (profile + orchestration preset + telemetry capture)
- [ ] Dry run and record demo
- [ ] Draft and publish DEV submission post
- [ ] Optional: publish second DEV write-up track post

---

## 11) Notes on Grounding

This strategy was grounded against current repository architecture and runtime seams, including:

- current architecture doc
- model profile system
- chat model override behavior
- DSPy configuration and optimization setup
- Chirp manager + chirp_create implementation path
- Vision model catalog and video model listing/estimate surfaces

