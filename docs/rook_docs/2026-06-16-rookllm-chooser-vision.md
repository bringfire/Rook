# RookLLM Chooser — Vision

> **Status:** Vision / north star **for the Model Control phase** — *not* the
> product north star. Not a spec. The Model Control slices and the tool-calling
> spike ladder up to this.
> **Phase:** Model Control. **Date:** 2026-06-16.
> **Subordinate to:** the Rook north-star topology
> (`docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`). The Chooser
> is a **dependency and enabler** of that architecture's bottom tier — the "many
> cheap local-model agents at ~$0 doing in-file micro work" is only real if local
> models are *autonomous-grade*, which is exactly what this Chooser's capability
> axis measures and the spike gates. It enables the north star; it does not
> replace or compete with it.

## One-liner

A Rook-native chooser that — given the user's hardware and the *current* model
landscape — recommends and (agent-mediated) selects the right LLM for the task,
distinguishing what merely **runs** from what can actually **drive Rook's agent
loop**.

## Why this is the destination

Rook's local-model story only works if a user can land on a model that both
(a) fits their hardware and (b) is tool-capable enough for the work. Static
advice rots — models ship weekly — and "fits" ≠ "can drive the agent loop." The
chooser is the thing that makes the visibility, agent-setting, spike, and llmfit
add up to **one coherent feature** instead of four loose parts.

## Two axes (the core idea)

- **Fit axis** — what runs on this hardware, how fast, and does it *claim*
  tool_use. Source: **llmfit** (catalog + hardware presets + simulation +
  tok/s benchmarks). Guidance and candidate generation — *never* the authority on
  agentic fitness.
- **Capability axis** — does the model actually drive Rook's multi-tool worker
  loop (clean tool calls, completion, no runtime/template parse traps). Source:
  **Rook's own measurement**, seeded by the tool-calling spike and enriched over
  time ("record corrections, not successes").

**The chooser = fit × capability.** llmfit picks candidates; Rook's measured data
decides.

## The intent-aware rule (lock this in)

The chooser does **not** output "use model X." It outputs intent-scoped verdicts:

- **assist-grade** — fine for human-in-the-loop chat (light tool use).
- **autonomous-grade** — reliable for unattended planner/worker loops.

A model can be assist-grade and *not* autonomous-grade. Collapsing the two is the
failure mode that burns users; distinguishing them is what makes the chooser
*Rook's*, not a generic fit tool.

## How the pieces converge (already in flight)

- **Slice 1 (shipped, [PR #257](https://github.com/bringfire/Rook/pull/257))** —
  read-only model visibility = the chooser's **feedback surface**.
- **Slice 2 (next)** — agent-mediated per-conversation model setting = the
  chooser's **hands**. Agent sets, visibility reports, user instructs in NL — *not
  a dropdown*. Needs its own brainstorm/spec.
- **Tool-calling spike (recorded)** — generates the capability-axis **seed data**;
  gates *autonomous-grade*. Needs capable-tier hardware (24 GB+).
- **llmfit (fork cloned)** — fit-axis guidance; adopt **data only**, no Rust
  engine dependency. MIT.
- **Slice 3 (later, gated by spike)** — whole-stack profile switching (file write
  + DSPy reconfigure + security).

## The updatable knowledge layer

The chooser's data is a **model-fitness knowledge store** (fit from llmfit's
catalog × Rook-measured capability), updatable at runtime like Rook's other
knowledge stores — refreshable without a Rook release. This is the *existing*
knowledge-store pattern, not a new system.

## v0 caution

A v0 could surface llmfit fit-guidance to the agent today — but only clearly
labeled **fit-only**. A fit-only recommendation will confidently suggest models
that can't drive the loop. **Do not let a fit-only v0 wear the "RookLLM Chooser"
name**; the name implies the capability axis, which the spike must fill first.

## Sequence

**Slice 2 (agent-mediated setting + feedback) → spike (capability data, on
capable-tier hardware) → chooser (synthesis).** The chooser is the destination;
the spike unlocks it; Slice 2 is the next concrete step.

## Links

- Tool-calling spike: `docs/superpowers/specs/2026-06-16-local-model-tool-calling-spike.md`
- Model visibility design (Slice 1): `docs/superpowers/specs/2026-06-16-rook-chat-model-visibility-design.md`
- llmfit fork: `C:/Users/aryan/source/repos/Rook_llmfit` (MIT, [AlexsJones/llmfit](https://github.com/AlexsJones/llmfit))
- Routing source of truth: `mcp_server/src/rook/agent/model_profiles.py`
