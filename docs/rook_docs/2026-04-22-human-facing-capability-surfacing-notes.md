# Human-Facing Capability Surfacing — Notes

**Date:** 2026-04-22
**Status:** Working notes from discussion; not an implementation spec
**Related docs:**
- `2026-04-22-route-discovery-and-compose-exploration.md`
- `2026-04-11-knowledge-graph-v1.1-design.md`
- `2026-04-10-public-skills-brainstorm.md`

---

## 1. Core Reframe

The question is not primarily:

- "Should routes appear in the knowledge graph?"
- "Should this be a graph or a categorized list?"

The more fundamental question is:

**How does Rook surface latent capability to a human in the middle of real work?**

For a designer working in Rhino or Grasshopper, the relevant thoughts happen at
once:

- What can I do here?
- What can Rook do for me?
- What might help right now that I do not already have in mind?
- What usually comes next?

That means the problem is not conventional onboarding, and it is not a normal
button-bar affordance problem either. Discovery is continuous, even for expert
users.

---

## 2. Why Traditional UI Framing Feels Wrong

Rook is a semantic, bi-directional, LLM-mediated tool surface. That does not fit
cleanly into a traditional static button UI.

A normal button-based interface assumes:

- the capability set is already mostly known to the user
- recall is the main problem
- categories are stable and intuitive
- the user can navigate by command family or menu location

Rook breaks those assumptions:

- capability is broader and more latent
- some value is in surprising the user with useful adjacent possibilities
- many actions are compositional
- the same user may need discovery, comparison, explanation, and next-step help
  in the same moment

The likely shape is therefore neither pure chat nor pure buttons. It is closer
to a **guided semantic workbench** inside whatever host the user is already
using.

---

## 3. What The Human Actually Needs

The lived question is:

**"What might help me right now that I do not already have in mind?"**

That breaks into a few analytically separate but experientially overlapping
jobs:

- capability discovery
- situational relevance
- composition / workflow assembly
- predictability and trust
- reuse

These are different design problems, but they blur together in real work. The
important consequence is that the user-facing unit probably should not be a raw
HTTP route or MCP tool.

For human consideration, the better unit is a **normalized capability**:

- name
- what it helps with
- inputs required
- outputs produced
- risks / caveats
- adjacent follow-ups
- examples
- maturity / confidence

Underneath, a capability may map to:

- a direct typed route
- an MCP tool
- a GH proxy action
- a script-backed move
- a multi-step workflow

---

## 4. Graph vs List

A categorized list is better for:

- inventory
- lookup
- scanning categories
- reading details quickly

A graph is only justified if the user is asking a relationship question such as:

- what lives near this?
- what tends to follow this?
- what bridges to another domain?
- what else is conceptually similar?

That means a graph is not automatically a good default capability surface.

The current knowledge graph edges are mostly **semantic relatedness**, not
workflow topology:

- UnifiedStore note edges come from persisted `note.links`
- command edges come from `related_commands`
- `similar_to` edges are conceptual similarity links for components

Those are real stored relationships, but they are not the same as:

- co-usage
- next-step tendencies
- valid composition paths
- intent-level adjacency

So the graph is best understood as a knowledge map, not yet a route-composition
surface.

---

## 5. Selection Alone vs Session Context

Selection alone can still provide useful signal.

From selection, Rook can infer:

- object types and mixtures
- geometry affordances
- valid / invalid input readiness
- likely nearby operations
- domain cues from metadata
- local risk signals

Selection answers:

- what are these things?
- what operations are plausible?
- what is ruled out?

But selection alone cannot reliably answer:

- why these objects are selected
- which of several plausible actions is intended
- what workflow phase the user is in
- whether this is exploratory, corrective, or final

Useful shorthand:

- **Selection gives the local board state**
- **Session/history gives the game being played**

---

## 6. Session Recorder Importance

The session recorder should remain in scope for this exploration.

It is one of the strongest sources of evidence about what the human was
actually doing, not just what tools exist.

There are at least two materially different recording surfaces:

- native Rhino session recording
- GH session history

The native recorder is stronger for chronological command/action trace.

The GH recorder is richer semantically:

- actions
- params
- outcomes
- created/affected/deleted components
- connections made/removed
- notes
- plans
- applied patterns

This suggests different uses:

- Rhino-native: contextual hint source and activity trace
- Grasshopper: workflow-learning substrate, reflection source, and pattern input

The recorder is most valuable as a signal source for:

- contextual suggestion ranking
- next-step hints
- recovery hints
- example grounding
- pattern promotion

It should not be treated as a complete recommendation engine by itself.

---

## 7. Chat History As Context

If the host UI is Codex Desktop, Claude Code, VS Code, or a similar text-first
surface, then the conversation itself becomes part of the real task context.

Without some representation of the conversation, an LLM loses:

- declared goal
- reframings
- corrections
- tradeoff preferences
- explicit acceptance/rejection of options

Thumbs up / thumbs down are not enough. They are useful as weak outcome labels,
but they do not explain:

- why something was helpful or unhelpful
- what the user was actually trying to do
- whether a suggestion was wrong, mistimed, too obvious, too risky, or just not
  relevant

The useful stack is:

- conversation text
- workspace / document / selection context
- action trace
- outcome trace
- optional explicit feedback

The important implementation note is that realtime prompts probably should not
consume raw transcript directly. Instead, the system should derive a compact
working-context object from transcript + state + session data.

---

## 8. Host-Agnostic Surface

Since the native Rook chat panel is slower and less capable than Codex Desktop,
Claude Code, and similar hosts, the primary product should not be framed as a
Rook-panel feature first.

The better framing is:

**Rook as a semantic suggestion layer that better hosts can consume.**

That implies host-agnostic serving APIs or equivalent internal interfaces such
as:

- what can help here?
- what next?
- explain this capability
- compare options
- find workflows

The host remains the UI.
Rook provides the semantic substrate.

---

## 9. Offline vs Realtime Separation

This appears to be the key architectural separation.

The useful mechanism is not realtime invention from raw logs. It is:

### Offline or asynchronous interpretation

Turn raw traces into grounded artifacts:

- normalized capabilities
- workflow episodes
- co-occurrence patterns
- next-step tendencies
- struggle points
- recovery patterns
- examples
- ranking features

### Realtime serving

Use the prepared artifacts plus live context to decide:

- what to suggest now
- how strongly to rank it
- how to explain it
- when to stay quiet

This separation is necessary because it keeps the live system:

- simpler
- more inspectable
- easier to tune
- less likely to hallucinate meaning from raw traces

The live interface should mostly retrieve and rank prepared semantic material,
not generate semantics from scratch every time.

---

## 10. Emerging Architecture Sketch

### Raw inputs

- capability metadata from routes/tools/workflows
- current document / selection state
- session recorder data
- transcript history from host conversations
- knowledge / pattern stores

### Processing layer

- correlate transcript + recorder into interaction episodes
- summarize intent / action / outcome
- normalize capabilities across route dialects
- compute affinities and next-step patterns
- extract recoveries and struggle patterns

### Serving layer

- lightweight contextual suggestion APIs
- capability explanation cards
- next-step retrieval
- comparison / workflow retrieval

### UI layer

- host-driven presentation in Codex / Claude / VS Code / etc.
- compact suggestion blocks
- drill-in details
- optional neighborhood/relationship views

---

## 11. Working Conclusions

- The main problem is not "route visualization." It is human-facing latent
  capability surfacing.
- The current graph may still be useful, but only if it is leveraged for
  relationship questions rather than inventory.
- Raw routes are probably the wrong human-facing unit. Normalized capabilities
  are better.
- Selection-only context is useful but incomplete.
- Session recorder data is important and should remain in scope.
- Chat history is a major source of intent/context and cannot be replaced by
  thumbs up/down alone.
- The system likely needs a strong separation between offline interpretation and
  realtime surfacing.
- The primary target should be host-agnostic support for better clients, not a
  Rook-panel-first UI.

---

## 12. Open Questions

- What is the minimum viable normalized capability model for human-facing use?
- Which live contexts should dominate ranking when they disagree:
  selection state, session activity, or stated conversational goal?
- How much host conversation history is needed for useful context without
  overloading privacy, storage, or prompt budgets?
- What is the smallest derived working-context object that makes Rook feel like
  it understands the ongoing task?
- Should the first shipped surface emphasize:
  - "what can help here?"
  - "what next?"
  - "compare options"
  - or a compact blend of the three

