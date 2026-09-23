# Contextual Capability Understanding — Design

**Date:** 2026-04-22
**Status:** Draft for debate and iteration
**Audience:** Bringfire, Codex, Claude, future implementation work
**Builds on:**
- `2026-04-22-human-facing-capability-surfacing-notes.md`
- `2026-04-22-route-discovery-and-compose-exploration.md`
- `2026-04-11-knowledge-graph-v1.1-design.md`
- `2026-04-10-public-skills-brainstorm.md`

---

## 1. Purpose

Define the core architecture for how Rook should understand what is happening
in a design session and determine what capabilities are relevant in context.

This document intentionally centers the **semantic substrate** rather than any
single user interface. UI surfaces are treated as thin consumers resting on top
of that substrate.

The goal is to produce a design and roadmap that can be debated, refined, and
implemented when ready.

---

## 2. Core Thesis

Rook should be built around **contextual capability understanding**.

That means the core system should answer:

- What is happening?
- What capabilities are relevant here?
- What is likely to help next?
- What evidence supports that?
- How should the recommendation or result be explained to a human?

This is a broader and more durable framing than:

- route discovery
- graph visualization
- a capability list UI
- a Rook-native chat panel

Those are all downstream consumers or expressions of the core system.

### Design Principle

The system should be:

- **semantically thick in the middle**
- **presentation-thin at the edges**

This lets the same substrate serve:

- Codex Desktop
- Claude Code / VS Code
- a future Rook panel
- autonomous or semi-autonomous agents

---

## 3. Problem Statement

Rook has broad latent capability, but the current system does not provide a
strong way to understand or surface that capability in context.

The user problem is not simply:

- "What routes exist?"

It is closer to:

**"What might help me right now that I do not already have in mind?"**

For a designer in Rhino or Grasshopper, several questions collapse together:

- What can I do here?
- What can Rook do for me?
- What usually comes next?
- What am I overlooking?
- Which of these options is safest or most relevant?

The current challenge is therefore not just onboarding, not just route
inventory, and not just UI discovery. It is the absence of a strong substrate
for understanding **task context + relevant capability + likely next move**.

---

## 4. Non-Goals

This design is not:

- a commitment to a graph-first UI
- a commitment to a categorized list UI
- a commitment to route nodes in the existing knowledge graph
- a replacement for current MCP/tool catalogs
- an implementation plan
- a promise that the native Rook chat panel becomes the primary surface

This design does not assume:

- that raw routes are the correct human-facing unit
- that the knowledge graph is the correct primary capability interface
- that implicit thumbs up/down feedback is sufficient

---

## 5. Conceptual Frames

Several frames surfaced during discussion. They are all relevant, but not all
should occupy the same level in the architecture.

### 5.1 Human-Facing Latent Capability

The immediate user-facing problem is surfacing latent capability to humans who
are already in the middle of real work.

### 5.2 Host-Agnostic Semantic Support

The primary host today is often Codex Desktop, Claude Code, or another external
surface rather than the Rook-native panel. The core substrate should therefore
be host-agnostic.

### 5.3 Agent-First Future Relevance

Even if the human is less in the loop later, design intent still matters
because outputs remain human-consumed. The same substrate should transfer from
human-facing suggestion support into agent-facing planning, retrieval, and
explanation support.

### 5.4 Offline Interpretation + Realtime Serving

The system should not try to infer meaning from raw exhaust during live
interaction. It should transform raw traces into better semantic artifacts
offline or asynchronously, then use those artifacts during realtime serving.

---

## 6. Core Objects

The load-bearing part of this system is not a graph node or a route registry.
It is a set of derived semantic objects.

### 6.1 `NormalizedEvent`

Smallest common unit of evidence from any stream.

Fields should likely include:

- `event_id`
- `timestamp`
- `source`
  - `codex`
  - `claude`
  - `rhino_session`
  - `gh_session`
  - `selection_snapshot`
  - `capability_catalog`
- `project_cwd`
- `document_path`
- `thread_or_session_id`
- `event_type`
- `payload`
- `attribution_confidence`

### 6.2 `InteractionEpisode`

Primary unit of interpretation.

An episode represents a bounded stretch of work with coherent intent,
context, actions, and outcome.

Likely fields:

- `episode_id`
- `project_cwd`
- `document_path`
- `start_time`
- `end_time`
- `conversation_refs`
- `session_refs`
- `declared_goal`
- `goal_revisions`
- `current_focus`
- `action_trace`
- `outcome`
- `workflow_phase_guess`
- `struggle_markers`
- `recovery_markers`
- `confidence`

### 6.3 `Capability`

Human- and agent-facing normalized unit of what Rook can do.

A capability may map to:

- one route
- one MCP tool
- several routes/tools
- a script-backed action
- a higher-level workflow

Likely fields:

- `capability_id`
- `name`
- `description`
- `kind`
  - `atomic`
  - `composite`
  - `workflow`
- `backing_actions`
- `input_requirements`
- `output_types`
- `domain_tags`
- `risk_level`
- `maturity_level`
- `examples`
- `adjacent_capabilities`
- `known_failure_modes`

### 6.4 `SuggestionCandidate`

Potential item to surface in a live context.

Likely fields:

- `capability_id`
- `candidate_type`
  - `help_here`
  - `next_step`
  - `compare_option`
  - `warning`
  - `recovery`
- `relevance_features`
- `evidence_refs`
- `explanation`
- `rank_score`
- `serving_confidence`

### 6.5 `OutcomeSignal`

Feedback artifact used for learning and evaluation.

Likely fields:

- `suggestion_ref`
- `surfaced_at`
- `used`
- `ignored`
- `accepted_explicitly`
- `rejected_explicitly`
- `subsequent_success`
- `subsequent_failure`
- `undo_or_reversal`
- `reformulation_after_suggestion`
- `feedback_source`

---

## 7. Signal Sources

The system should consume multiple evidence streams. No single stream is
sufficient.

### 7.1 Host Conversation History

Provides:

- declared goals
- reframings
- corrections
- tradeoff preferences
- explicit approval / rejection of options

Examples:

- Codex session logs under `~/.codex/sessions/...`
- Claude project-scoped transcript/event logs under `~/.claude/projects/...`

### 7.2 Session Recorder Data

Provides:

- chronological actions
- source attribution
- command/tool outcomes
- created/deleted/affected geometry or components
- applied patterns in GH flows

Important distinction:

- native Rhino session recording is better for command/action trace
- GH session history is richer semantically and more workflow-aware

### 7.3 Live Document / Selection State

Provides:

- what is currently selected
- what object/component types are present
- local affordances and constraints
- readiness for particular capabilities

Selection gives local board state, but not full intent.

### 7.4 Capability Metadata

Provides:

- what tools/routes/workflows exist
- parameter contracts
- categories/tags
- descriptions
- capability maturity and caveats

### 7.5 Knowledge / Pattern Stores

Provides:

- prior patterns
- anti-patterns
- recipes
- examples
- known contexts and failure modes

---

## 8. Why Thumbs Up / Down Are Not Enough

Thumbs are useful but weak.

They can indicate:

- broad helpful / unhelpful sentiment

They do not reveal:

- actual user intent
- whether the problem was bad ranking or bad execution
- whether a suggestion was wrong or merely mistimed
- whether something was ignored because it was obvious, risky, irrelevant, or
  too verbose

They should be treated as one signal among many, not the core grounding
mechanism.

---

## 9. Architecture Overview

The proposed system has four major layers plus thin consumers.

### 9.1 Ingestion Layer

Collect raw evidence from all streams.

Responsibilities:

- read host conversation logs
- read session recorder outputs
- capture current document/selection snapshots
- export capability metadata from route/tool/workflow registries

Output:

- raw append-only event streams

Implementation principle:

- this layer should be built as a **local observability subsystem**
- it should not be tightly coupled to any one host or UI
- it should treat external sources as explicit integrations, not as ad hoc file
  scraping embedded throughout the codebase

### 9.2 Normalization Layer

Convert all raw streams into `NormalizedEvent` records.

Responsibilities:

- unify timestamps
- map source-specific payloads into common envelopes
- preserve provenance
- maintain lightweight confidence about attribution quality

Output:

- normalized, queryable cross-stream event table

### 9.3 Correlation + Interpretation Layer

Turn normalized events into bounded task windows and then into
`InteractionEpisode`s.

Responsibilities:

- correlate by time window, `cwd`, document, and session/thread ids
- split long streams into coherent episodes
- summarize declared goal and revisions
- infer workflow phase
- identify struggle and recovery segments

This layer is the core of contextual understanding.

### 9.4 Insight Derivation Layer

Convert episodes into reusable semantic artifacts.

Responsibilities:

- maintain normalized capabilities
- generate example episodes per capability
- learn next-step tendencies
- derive co-usage affinities
- identify struggle-recovery patterns
- produce ranking features for serving

Output:

- capability and pattern indexes
- serving-ready summary stores

### 9.5 Realtime Serving Layer

Use prepared semantic artifacts plus live context to answer current questions.

Responsibilities:

- candidate generation
- ranking
- explanation
- next-step suggestion
- comparison support
- recovery hinting

Output:

- compact, explainable suggestion payloads for hosts or agents

### 9.6 Thin Consumer Layer

Consumers may include:

- Codex Desktop
- Claude Code / VS Code
- future Rook-native surfaces
- autonomous agents

Consumers should not own semantic interpretation. They should mainly render,
request, and interact with the substrate.

---

## 10. Offline / Asynchronous Pipeline

This is the load-bearing pipeline.

### Stage 1: Ingest

Read and persist raw evidence from:

- host logs
- session logs
- document/selection state snapshots
- capability export sources

### Stage 2: Normalize

Create `NormalizedEvent`s from each source.

### Stage 3: Correlate

Join events into candidate work windows using:

- timestamp proximity
- shared `cwd`
- document path
- explicit session/thread ids where available

### Stage 4: Segment

Partition candidate windows into coherent `InteractionEpisode`s.

### Stage 5: Summarize

For each episode, derive:

- declared goal
- action sequence
- context state
- outcome state
- workflow phase guess
- struggle/recovery markers

### Stage 6: Extract Candidate Insights

Produce draft artifacts such as:

- capability examples
- next-step patterns
- co-usage affinities
- recovery hints
- warnings

### Stage 7: Aggregate

Accumulate observations across episodes using:

- counts
- recency decay
- success rate
- risk rate
- false-positive rate

### Stage 8: Publish

Write serving-ready indexes and lookup structures.

### Suggested Cadence

- nearline: after session close or every few minutes
- nightly: aggregate and refresh indexes
- weekly: evaluate, prune, promote, and review

### Durability Requirement: Replayability

This pipeline should be replayable end to end.

That means the system must preserve enough information to:

- re-run normalization when source formats change
- re-run episode correlation when heuristics improve
- re-run insight extraction when schemas evolve
- rebuild serving indexes without losing raw evidence

Without replayability, the system will become brittle as soon as early schema
or interpretation choices change.

---

## 11. Realtime Serving Model

The live system should be conservative and lightweight.

It should not interpret raw logs from scratch.

### 11.1 Inputs

- live host query or current task text
- current selection/document snapshot
- recent episode summary
- capability and pattern indexes

### 11.2 Outputs

The first useful live queries are likely:

- `what_can_help_here`
- `what_next`
- `compare_options`
- `explain_capability`
- `find_workflows`

### 11.3 Candidate Generation

Candidates should come from:

- selection-affordance match
- recent-episode next-step match
- capability tag/domain match
- prior successful episode similarity

### 11.4 Ranking

Ranking should be based on:

- contextual fit
- success likelihood
- risk
- novelty vs obviousness
- timing
- explanation quality / evidence quality

### 11.5 Explanations

Every suggestion should be explainable in human terms:

- why it is relevant
- what it needs
- what it produces
- what makes it risky or safe
- what evidence supports it

---

## 12. Evaluation Strategy

The system needs both offline and online evaluation.

### 12.1 Offline Evaluation

Use held-out `InteractionEpisode`s to test:

- whether the eventually useful capability was in the candidate set
- whether it ranked near the top
- whether the next-step pattern matched later episode behavior
- whether recovery hints match known struggle-recovery outcomes

### 12.2 Online Evaluation

Measure:

- suggestion invocation rate
- suggestion ignore rate
- reduction in retries
- reduction in reformulations
- improved task completion
- explicit feedback where available
- undo/reversal after suggestion

### 12.3 Human Review Loops

Some artifacts should remain reviewable before promotion:

- newly derived high-impact patterns
- warnings and anti-patterns
- merged/split capabilities
- deprecation and adjacency changes

---

## 13. Consumer, Security, and Deployment Design

The first implementation step should be designed with real consumers and
installation realities in mind.

### 13.1 Source Adapters As Explicit Integrations

The system should not directly depend on hardcoded knowledge of arbitrary host
storage layouts scattered across the codebase.

Instead, each source should be represented by a dedicated adapter such as:

- `CodexAdapter`
- `ClaudeAdapter`
- `RhinoSessionAdapter`
- `GHSessionAdapter`

Each adapter should own:

- install detection
- path discovery
- source-specific parsing
- source/schema version awareness
- emitted event provenance
- health/status reporting

The core pipeline should only consume normalized output and adapter metadata.

### 13.2 Local Install Detection

Install detection should be explicit and inspectable.

The system should:

- detect whether a supported host/source appears to be installed
- report where it was found
- report confidence and any ambiguity
- avoid assuming that one machine layout is universal

Detection should produce a source inventory rather than silently enabling
 ingestion.

### 13.3 Consent and Security

Host transcript ingestion is sensitive local telemetry and should be treated as
such.

Requirements:

- explicit opt-in per source
- clear explanation of what is being read
- easy enable/disable per source
- local-only by default
- support for session-only or project-only modes if needed later
- ability to delete and rebuild derived artifacts
- preference for redacting obvious secrets or sensitive payloads before
  downstream use when practical

Security posture:

- raw source data stays local
- normalized events stay local
- derived insights stay local
- export/sharing must be explicit, not implicit

### 13.4 Deployment Shape

This should be deployed as a Rook-owned local subsystem, not as hidden logic
buried in one particular host integration.

Suggested shape:

- source registry
- install detector
- permission manager
- ingestion runner
- normalized event store
- replay/backfill tools
- status/health API

This keeps the architecture stable even if external host file layouts change.

### 13.5 Reprocessing and Versioning

Every normalized event should preserve enough provenance to support rebuilds.

Likely fields to preserve:

- source identifier
- source location or stable reference
- adapter version
- source payload schema version if known
- normalization timestamp
- parsing warnings/errors if any

This supports:

- partial reparse
- full rebuild
- migration to improved schemas

### 13.6 First Durable Implementation Target

The first implementation should be:

**a versioned, replayable event-ingestion layer that converts conversation and
session-recorder streams into canonical `NormalizedEvent`s**

This should come before:

- UI work
- graph/list capability surfaces
- adaptive ranking
- suggestion rendering

The first durable deliverable likely includes:

- canonical schema definitions
- source adapters
- append-only normalized event storage
- ingestion/backfill runner
- source detection and permission model
- basic audit/status reporting

---

## 14. Roadmap

This roadmap is conceptual and should be refined before implementation.

### Phase 0: Instrumentation Audit

Goals:

- enumerate existing host transcript sources
- enumerate session recorder outputs
- verify timestamp quality and join keys
- define privacy and retention boundaries
- define adapter boundaries and install-detection approach

Deliverables:

- source inventory
- event source map
- joinability assessment
- security/consent assumptions
- first adapter registry design

### Phase 1: Event + Episode Substrate

Goals:

- define `NormalizedEvent`
- define `InteractionEpisode`
- build normalization pipeline
- build replayable storage
- implement first source adapters

Deliverables:

- event schema
- episode schema
- normalized event store
- first pass ingestion runner
- first pass episode builder
- source health/status visibility

### Phase 2: Capability Normalization

Goals:

- normalize tools/routes/workflows into `Capability`
- define backing-action relationships
- identify maturity/risk/example fields

Deliverables:

- capability schema
- capability exporter
- first pass catalog

### Phase 3: Insight Derivation

Goals:

- derive examples, affinities, next-step patterns, recovery patterns
- build serving-ready indexes

Deliverables:

- candidate insight artifacts
- aggregate scoring model
- refresh cadence

### Phase 4: Realtime Serving

Goals:

- implement host-agnostic serving interface
- support first contextual queries

Deliverables:

- serving API or equivalent internal service
- first host-integrated suggestion payloads

### Phase 5: Thin Surfaces

Goals:

- support Codex / Claude suggestion surfaces first
- defer heavier visual surfaces until the substrate proves useful

Deliverables:

- first contextual suggestion UX
- optional richer inspection surfaces later

---

## 15. Recommendations

### Recommendation 1

Treat `contextual capability understanding` as the primary system.

### Recommendation 2

Treat UI layers, including graph/list/panel ideas, as thin consumers.

### Recommendation 3

Prioritize the event and episode substrate before route visualization work.

### Recommendation 4

Use conversation history, session recorder data, and live state together.
Do not rely on any one of them alone.

### Recommendation 5

Separate offline/asynchronous interpretation from realtime serving.

### Recommendation 6

Build the first implementation as a local, adapter-based, replayable ingestion
subsystem with explicit consent and source visibility.

---

## 16. Open Questions

- What is the minimum viable `Capability` model?
- What should dominate ranking when signals disagree:
  - declared conversational goal
  - session activity
  - current selection state
- How much host transcript history should be carried into the serving layer?
- What is the smallest useful working-context object for live use?
- When should the system stay quiet rather than suggest?
- Which artifacts require explicit human review before promotion?
- What should the first local storage format be for normalized events:
  JSONL, SQLite, or a hybrid?
- How much raw source material should be retained vs summarized?
- Which source adapters are in the first supported set, and which remain
  experimental?

---

## Appendix A: Graph vs List

A categorized list is strong for inventory and lookup.

A graph is only justified if relationship questions matter:

- what is near this?
- what tends to follow this?
- what bridges domains?

The current graph mostly reflects semantic relatedness, not workflow topology.
Therefore:

- a graph may still be useful later
- it should not be treated as the center of this design

---

## Appendix B: Route Discovery vs Capability Understanding

Route discovery remains a valid sub-problem, but it should be nested under the
broader capability model.

Humans should likely reason over normalized capabilities rather than raw route
surfaces.

Routes are still important as backing metadata, implementation targets, and
possible evidence sources.

---

## Appendix C: Session Recorder + Transcript Pairing

Session recorder data and host transcript data together provide richer context
than either alone.

Session recorder provides:

- what happened

Transcript provides:

- why it was being attempted

Together they support intent-to-action episode construction.

---

## Appendix D: MAB / Online Adaptation

MABWiser may be useful later in the realtime ranking layer as an adaptive
exploration/exploitation mechanism.

It is not the core interpretation mechanism and should not drive the upstream
pipeline design.

Use it, if at all, as:

- a downstream ranker among known candidates
- an adaptive learner over reward signals

Not as:

- the event interpretation layer
- the capability normalizer
- the source of semantic understanding

---

## Appendix E: Agent-First Relevance

If Rook becomes more agent-first over time, this substrate remains relevant.

What changes is the primary consumer:

- human-first world: suggestions and explanations for users
- agent-first world: retrieval, planning support, ranking, and explanation for
  agents

The same middle layer should serve both.
