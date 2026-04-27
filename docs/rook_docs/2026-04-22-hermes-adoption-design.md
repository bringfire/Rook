# Hermes Adoption for Rook — Design Note

**Date:** 2026-04-22
**Status:** Draft for prioritization, not implementation-ready
**Audience:** aryan, Codex, Claude, future implementation work
**Related:**
- `Rook/CLAUDE.md`
- `Rook/docs/CURRENT_ARCHITECTURE.md`
- `Rook/mcp_server/src/rook/learning/typed_reflection.py`
- `Rook/mcp_server/src/rook/learning/gh_session_history.py`
- `Rook/mcp_server/src/rook/agent/conductor.py`
- `Rook/mcp_server/src/rook/doctor.py`

---

## 1. Purpose

Capture what is genuinely worth adopting from `hermes-agent`, and correct the
first-pass mapping against Rook's live architecture.

This note is intentionally a **design-track prioritization memo**, not a PR
scope. The goal is to preserve the insight cleanly and avoid losing it to chat
history.

---

## 2. Core Conclusion

Hermes is interesting for Rook, but the value is **not** "copy Hermes'
self-improving agent whole cloth."

The durable value is narrower:

- a **background review scheduler**
- a **security/content guard** for agent-authored or imported procedural assets
- a **cross-session recall surface** over raw session transcripts

The important correction is that Rook already has substantial learning
infrastructure:

- synchronous failure reflection via `TypedReflection`
- persistent GH session recording via `GHSessionRecorder`
- draft pattern extraction via `gh_reflect`
- explicit correction recording via `knowledge_record`

So the adoption target is **missing orchestration and retrieval glue**, not a
replacement learning substrate.

---

## 3. What Rook Already Has

### 3.1 Failure reflection already exists

`TypedReflection` already maps failures into the Rook taxonomy:

- `PLANNING`
- `ROUTING`
- `PARAMETER_SYNTHESIS`
- `COMMAND_EXECUTION`
- `INTERACTIVE_PROMPT`
- `WRONG_RESULT`
- `TIMEOUT`

and emits `knowledge_record`-compatible correction payloads.

This is already wired synchronously inside `IntentOrchestrator.run()` and
`run_typed()`. Any Hermes-inspired batch loop must treat that path as the
ground truth, not as missing functionality.

### 3.2 GH reflection already exists, but is approval-gated

Rook already has:

- `gh_session_note`
- `gh_reflect`
- `gh_save_pattern`

This matters because Hermes' "background skill review" cannot be mapped
directly to auto-saving patterns without violating the current Rook contract:
`gh_reflect` returns **drafts**, and `gh_save_pattern` is intentionally the
approval step.

### 3.3 Session storage is already split across two substrates

Rook does **not** have one unified session store:

- native Rhino command/MCP session history lives under `%APPDATA%/Rook/sessions/`
- GH learning sessions live under `knowledge/gh/sessions/`

Any Hermes-style session recall surface must ingest both or explicitly choose
one. A design that assumes a single existing JSON session corpus is incomplete.

### 3.4 `conductor.py` is not the per-agent execution loop

The current `Conductor` is a **fleet coordinator for parallel spawned agents**.
It is instantiated from `spawn.py` for swarm runs and monitors cross-agent
failures.

It is not the right default home for per-turn or per-execution background
review nudges. Those nudges belong closer to:

- `IntentOrchestrator`
- `BaseAgent`
- `chat_runner`
- or a new narrowly scoped review service

depending on which evidence stream is being reviewed.

### 3.5 Rook does not currently own runtime skill loading semantics

Rook currently distributes skills by copying repo-owned skill trees into client
skill roots via install/doctor flows:

- `~/.claude/skills/`
- `~/.agents/skills/`

Rook does not currently implement a runtime "merge product skills + overlay
skills" loader. That means an overlay proposal is architecturally plausible,
but it is not a drop-in extension of an existing in-process loader.

---

## 4. Hermes Pieces Worth Adopting

## 4.1 Background review scheduler

Hermes' strongest transferable idea is the scheduler pattern:

- cheap periodic trigger
- quiet background review
- no interruption of the main task
- short-circuit when nothing is worth saving

What should carry over is the **scheduler shell**, not Hermes' specific review
prompts or its memory/skill semantics.

### Rook adaptation

The scheduler should review Rook-native evidence and dispatch only to Rook
surfaces such as:

- `knowledge_record`
- `gh_session_note`
- `gh_reflect`

The first implementation slice should probably be **observe-only or
note-producing**, not auto-saving permanent patterns.

## 4.2 Security/content guard

Hermes' `skills_guard.py` threat bank and install-policy model are worth
lifting, with one rename:

- use a general name like `content_guard.py`

This should cover more than skills:

- agent-authored skills if that lands
- imported recipe bundles
- user-supplied procedural content that may later be injected into prompts

This is useful even if agent-authored skill creation never ships.

## 4.3 Session recall over raw transcripts

Hermes' best pure retrieval idea is the FTS5 recall flow:

1. lexical search over archived conversations
2. truncate around actual match positions
3. summarize the relevant window instead of dumping raw transcripts

Rook has curated knowledge retrieval already. It does **not** have a strong
"what did we figure out last month about X?" surface over raw sessions.

This is a real gap.

---

## 5. Design Corrections to the First-Pass Proposal

### 5.1 Do not host the review loop in `agent/conductor.py`

That file is fleet-level swarm infrastructure. Putting per-execution learning
nudges there would mix:

- single-agent learning review
- cross-agent systemic-failure monitoring

Those are different responsibilities and should stay separate.

### 5.2 Do not auto-call `gh_save_pattern` from a background loop

`gh_reflect` is explicitly a draft-producing, human-review-oriented surface.
Auto-saving patterns in a background loop would silently change Rook's current
approval model.

If unattended review is added, the safe early versions are:

- `gh_session_note` only
- or `gh_reflect` draft creation without auto-save
- or a new queue of review candidates awaiting explicit approval

### 5.3 Do not describe session recall as one-store work

The first-pass sketch said "Rook's existing JSON session store" as if there
were one. There are two relevant stores with different producers and purposes.

The first design question is therefore:

- dual-source ingestion into one FTS sidecar
- or native-only first
- or GH-only first

### 5.4 Do not assume a Rook-side skill overlay loader already exists

An overlay root like `~/.rook/skills/` may still be the right future design,
but it implies a new ownership model:

- install/sync semantics
- conflict policy
- client compatibility
- provenance

That is a separate design task, not a trivial lift of Hermes'
`skill_manage`.

### 5.5 Do not batch `TypedReflection`

`TypedReflection` already runs synchronously per intent execution.

The background review loop should consume the artifacts produced by execution
and session recording; it should not simply replay `TypedReflection` over the
same results again.

---

## 6. Prioritized Adoption Order

## Tier 1 — Highest-leverage candidates

### A. Generalized content guard

Smallest clean adoption surface.

Why first:

- low coupling
- useful even without other Hermes features
- reduces risk for any future agent-authored/imported content path

### B. Session recall

Most user-visible gap Hermes can help close.

Why second:

- adds a capability Rook does not currently have
- complements, rather than fights, the existing curated knowledge stores
- can stay read-only and low-risk

### C. Background review scheduler

Useful, but should follow only after the review targets are sharply defined.

Why third:

- highest orchestration ambiguity
- easiest to mis-wire into the wrong layer
- easiest place to accidentally bypass Rook's current approval boundaries

## Tier 2 — Revisit only after a dedicated design pass

### A. User-overlay / agent-authored skills

Potentially valuable, but not ready for direct adoption.

Requires:

- runtime ownership model
- client-surface compatibility story
- provenance format
- approval UX
- shadow/override rules

### B. Frozen-snapshot memory patterns

Worth revisiting only if prompt caching and cache invalidation become a concrete
performance bottleneck in the conductor/agent runtime.

## Tier 3 — Skip for now

- pluggable MemoryProvider architecture
- delegate-tool patterns
- skills hub
- training / trajectory compression features
- messaging gateway surfaces

These do not line up with the current Rook bottlenecks.

---

## 7. Recommended First Eventual Slice

When this topic is promoted, the first implementation slice should be one of
these narrow options:

### Option A — `content_guard.py`

Port/adapt Hermes' guard logic into a generalized scanner with tests.

### Option B — `session_recall`

Add a read-only MCP surface over archived sessions backed by an FTS sidecar.
The first version may choose native sessions only or GH sessions only, but it
must state that boundary explicitly.

### Option C — background review candidate queue

Add a quiet review loop that produces:

- `gh_session_note` entries
- or review candidates / drafts

but does **not** auto-save patterns yet.

---

## 8. Non-Goals

This note is not:

- a commitment to implement Hermes-style self-improvement wholesale
- a justification for auto-saving patterns without approval
- a commitment to agent-authored skills
- a PR scope

---

## 9. Queue Decision

Park this as an **architecture item with concrete future slices**, not a
start-now feature.

It is valuable, but it should not displace the current hotspot-driven
prioritization rhythm until one of the following is true:

- substrate observations identify a learning/retrieval bottleneck this solves
- user direction explicitly promotes it
- a concrete adjacent task makes one narrow slice cheap to bundle

