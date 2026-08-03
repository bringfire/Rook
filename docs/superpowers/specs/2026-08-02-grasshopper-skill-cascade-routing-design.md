# Grasshopper Skill Cascade Routing Design

**Date:** 2026-08-02

**Status:** Proposed

**Decision:** Replace the mandatory four-stage Grasshopper cascade with a routed three-skill workflow. Retain corrected design and execution skills, make planning optional, remove consolidation from user-facing skill surfaces, and keep Wasp behind one compact live-admission contract.

## Goal

Make the shipped Grasshopper skills accurately describe Rook's supported MCP surface and choose only the workflow stages that add value to the request.

The result is guidance, not a runtime router:

```text
Clear bounded request ---------------------------------> Execute
Ambiguous request -> Design -> user decision ----------> Execute
Large or high-risk request -> Design? -> Plan -> gate -> Execute
Wasp request -> live admission -> supported route or stop
```

Skill descriptions, completion options, and handoff text express this routing. No dispatcher, orchestration service, state machine, or generalized skill framework is added.

## Audit basis

The current surface is internally inconsistent:

- Codex installs design-grasshopper, plan-grasshopper, and execute-grasshopper, but not consolidate.
- execute-grasshopper nevertheless invokes consolidate unconditionally.
- README and the Claude session-start hook still advertise a mandatory four-stage cascade.
- design, plan, and execute use Claude-style pseudo-calls such as Skill(...) and Read(...) that are not a portable cross-client handoff contract.
- The skills name gh_delete and gh_set_value as though they were declared MCP tools. Internal dispatcher compatibility cases still exist, but neither name is in the declared MCP schema. gh_query is absent.
- Plan and execute both prescribe global cleanup and grouping.
- Knowledge lookup is repeated and treated as identity evidence even though installed guidance correctly makes knowledge advisory and live component metadata authoritative.
- Wasp references contain unadmitted component assumptions, stale calls, and design-phase Rhino mutation.

Codex and Claude also expose different catalogs by design. Codex is installed with the lean profile; Claude is intentionally left on the full default profile. Lean is advertisement-only, and its four rook_tools_* gateways can search, read, and call admitted hidden tools. Corrected skills must therefore use one client-neutral rule: call a supported tool directly when exposed, otherwise use progressive discovery. This specification does not change either profile.

## Stage dispositions

| Skill | Disposition | Supported purpose |
|---|---|---|
| design-grasshopper | Retain with corrections | Optional, read-only co-design for ambiguous or open-ended work. |
| plan-grasshopper | Make optional/manual | Durable technical plan for large, high-risk, cross-session, or review-sensitive work. |
| execute-grasshopper | Retain with corrections | Canonical bounded Grasshopper mutation and verification workflow. |
| consolidate | Remove from the user cascade and shipped skill surfaces | Developer maintenance remains available through the existing MCP and DSPy implementation. |

The three retained skills do not automatically invoke one another through pseudo-tools. Each concludes with explicit next-step options. The active agent may continue in the same task when the next step is already authorized and the required input contract is satisfied.

## Authorization boundary

A direct request such as “build this definition,” “connect these components,” or “update this canvas” authorizes the bounded mutations necessary to fulfill that request. Execution does not ask for a redundant confirmation merely because it will mutate Grasshopper.

Additional confirmation is required only when:

- requirements remain materially ambiguous;
- the operation is destructive;
- pre-existing user content would be moved, grouped, disconnected, deleted, or otherwise changed;
- a missing capability requires a materially different implementation; or
- the requested scope must expand meaningfully.

Design and planning remain read-only. A design-stage Wasp scaffold is not an exception; any Rhino or Grasshopper preparation belongs to execution and follows the same authorization boundary.

## design-grasshopper contract

### Purpose

Use design-grasshopper when the user needs help choosing topology, behavior, constraints, alternatives, or acceptance criteria. A clear bounded brief does not need to pass through design.

### Input

- An ambiguous or open-ended Grasshopper goal.
- Optional current-document and Rhino-scene context.
- User constraints and preservation requirements.

### Behavior

The skill may inspect the current canvas, scene, live component catalog, and advisory knowledge. It must not mutate Rhino or Grasshopper.

Knowledge queries are optional and advisory. Exact component identity, GUIDs, and ports come from live gh_library and gh_batch_component_info evidence when technical grounding is needed. If those tools are hidden, the skill uses rook_tools_search, rook_tools_read, and rook_tools_call rather than pretending the calls are unavailable.

The design remains conceptual enough to survive a later live-state revalidation. It records:

- intent and success criteria;
- important inputs, outputs, and data-flow choices;
- alternatives considered and the selected approach;
- constraints, preservation boundaries, and unresolved decisions;
- whether Wasp or another optional dependency requires admission; and
- whether a durable implementation plan is warranted.

It does not manufacture exact GUIDs, volatile epochs, fixed canvas coordinates, or executable batches.

### Output and handoff

When a durable artifact adds value, write an approved design document under docs/plans. Otherwise a concise in-task decision record is sufficient.

Completion offers two supported routes:

- execute directly when the approved design is bounded and ordinary; or
- create an optional plan when the work meets the planning threshold.

There is no automatic Skill(...) handoff. If design is unavailable or intentionally skipped, a clear brief may proceed directly to execution.

## plan-grasshopper contract

### Purpose and admission

Planning is optional. Use it for work that is large, destructive, dependent on pre-existing topology, expected to span contexts, or important enough to review before mutation. Ordinary small and medium definitions use execution's lightweight in-memory preflight instead.

### Input

- An approved design, a clear specification, or an equivalent user-provided artifact.
- The target document identity and a fresh read-only structural snapshot when existing-canvas state matters.
- Ownership and preservation boundaries.

### Behavior

Planning performs no Rhino or Grasshopper mutation. It resolves current component identities and ports through live component metadata and current tool schemas. Advisory knowledge may add gotchas but cannot establish availability or correctness.

The plan uses supported gh_edit operations for create, set-values, connect, disconnect, group, and delete work. It does not emit undeclared gh_delete or gh_set_value calls, absent gh_query calls, or client-specific pseudo-handoffs.

For existing-canvas work, the plan records a structural baseline sufficient to detect drift, including target document identity, relevant component identities, relevant connections, ownership, and preservation constraints. It does not persist a snapshot epoch; epochs are volatile runtime concurrency tokens, and execution always obtains a fresh one immediately before mutation. Without the structural baseline, execution treats the plan as advisory and re-admits the live state before mutation.

The plan defines bounded batches, expected results, ownership, verification, and stop conditions. It may recommend grouping or layout for execution-owned components, but it does not prescribe unconditional global canvas cleanup.

### Output and handoff

The durable plan is an input option for execute-grasshopper, not an authorization token and not a promise that stale calls will be replayed literally. Completion offers execution after any required approval. It does not invoke execute through Skill(...).

If planning is unavailable or intentionally skipped, execute performs a lightweight equivalent preflight in the current task.

## execute-grasshopper contract

### Purpose and input

Execute is the canonical mutation stage. It accepts:

- a clear bounded brief;
- an approved design; or
- an optional technical plan.

### Admission before mutation

Execution always:

1. confirms the intended target document or host;
2. captures a fresh gh_snapshot and epoch;
3. resolves every unfamiliar component and relevant port from live metadata;
4. compares any supplied structural baseline with current state; and
5. identifies execution-owned state and preserved pre-existing state.

If a plan lacks a baseline or the live state has drifted, execution re-admits the current state. In-memory adaptation is limited to refreshing component identities or ports from authoritative live metadata and omitting operations that the live state proves are already satisfied. Semantic, topology, ownership, or preservation changes stop for approval. Execution never treats a stale artifact as stronger evidence than the live canvas.

### Mutation and ownership

Supported gh_edit operations are the preferred mutation surface. Hidden supporting tools are reached through progressive discovery when necessary.

Execution may group, move, retry, disconnect, or delete only components it created during the current execution unless the user's request explicitly authorizes changes to identified pre-existing content. No unconditional global gh_canvas_cleanup is allowed.

Each mutation response is processed as an ordered result with possible partial success. Execution records which operations committed, refreshes state and epoch as required, and retries only the failed or unapplied subset. It never replays committed operations after partial success.

Final verification uses a fresh snapshot plus relevant error, connection, or output inspection. Successful execution ends with a concise record of created or changed state, verification evidence, and any unresolved limitations.

### Termination

Successful execution terminates successfully without consolidation. There is no automatic knowledge write or consolidate handoff. Failure of, absence of, or inability to discover gh_consolidate cannot make a Grasshopper build fail.

If execution itself is unavailable because no admitted host, mutation tool, or required live component can be reached, the workflow stops without mutation. It preserves any useful design or plan artifact, identifies the missing boundary, and does not improvise through obsolete aliases or an unapproved transport.

## Consolidation retirement boundary

Remove the consolidate user skill completely from active cascade surfaces:

- delete .agents/skills/consolidate;
- delete .claude/skills/consolidate;
- ensure the curated installer Codex skill payload does not contain consolidate;
- remove its execute handoff and its user-facing README, quick-start, setup, hook, catalog, and post-install claims;
- remove corresponding public plugin and site claims during promotion; and
- exact-clean ~/.codex/skills/consolidate during every supported install and repair, regardless of Codex component selection.

The existing migration-specific retired Codex skill helper is extended with the exact consolidate name. Its established safety contract remains unchanged: canonical parent verification, lexical direct-child construction, non-following metadata, no globs, no sibling or parent deletion, idempotent absence, bounded per-target outcomes, and clear nonfatal failure reporting. No generalized cleanup framework is introduced, and no Claude or sibling Codex skill is removed from a user installation.

Retain unchanged:

- the gh_consolidate MCP schema and dispatch;
- DSPy consolidation implementation;
- knowledge stores and developer maintenance scripts;
- full-profile and progressive-discovery access to the real tool; and
- accurate developer-only maintenance documentation.

This is a workflow and product-surface decision, not a runtime capability purge. Existing internal gh_delete and gh_set_value compatibility cases likewise remain untouched.

## Wasp admission contract

Wasp remains optional experimental functionality pending focused admission. Replace the current executable Wasp recipe collection in shipped skill assets with one compact contract that retains useful conceptual vocabulary but no assumed executable graph.

Before any Wasp mutation, the active agent must:

1. verify a reachable Grasshopper host;
2. use gh_library to establish the exact minimum Wasp components required by the selected approach;
3. use gh_batch_component_info to establish their current GUIDs and input/output ports; and
4. stop on any missing, ambiguous, or incompatible result.

A locally installed Wasp folder, advisory knowledge entry, placeholder GUID, or old recipe is not admission evidence. The current detailed field, constraints, aggregate, scaffold, DisCo, save/load, and related executable fragments leave shipped skill assets. Useful conceptual distinctions may be condensed into the single admission reference.

If Wasp is unavailable, the stage performs zero Rhino and Grasshopper mutation. It reports the missing capability and offers either a user-managed installation/restart followed by another live preflight or a clearly identified non-Wasp approach. A conceptual Wasp design may be retained only when labeled non-executable.

Wasp-specific Rhino scaffolding, export, or external-service work occurs only during an authorized execution. This effort does not attempt to verify every historical Wasp recipe or promote Wasp to default support.

## Active guidance and mirrors

Correct active guidance in the private repository, including:

- README.md;
- QUICK_START.md;
- AGENT_SETUP.md;
- scripts/session-start.sh;
- installer Codex and Claude post-install guidance;
- .agents skill assets;
- .claude plugin skill assets; and
- installer/agent-assets/codex-skills.

The three retained skills and their active references use client-neutral language. Their roots under .agents/skills, .claude/skills, and installer/agent-assets/codex-skills must have the same recursive relative-file inventory and byte-identical contents. Do not add a skill generator or synchronization framework. One focused parity contract is sufficient.

Skill frontmatter descriptions state only the trigger conditions and scope for selecting that skill. Routing decisions, completion choices, and handoff behavior belong in the skill body rather than frontmatter.

The public rook-release repository is promoted only after the private implementation has been accepted. Its design, plan, execute, session hook, plugin catalog, and product-page copies must describe the same routed model and contain no consolidation handoff or stale Wasp execution guidance. Historical specifications, plans, reports, release evidence, and unrelated uses of the ordinary word “consolidate” remain untouched. Public work occurs in a separate promotion PR and is not part of, or a merge gate for, the private implementation PR.

There is no repository-wide string ban. Checks target exact retired identities, named active files, and the three retained skill roots.

## Focused permanent contracts

Use one cascade contract suite, plus the existing installer migration tests. Avoid a new verifier framework.

Permanent checks prove:

- design, plan, and execute exist in all intended private shipped mirrors;
- the three retained skill roots have exact recursive file-set and byte equality across .agents, .claude, and installer copies;
- consolidate is absent from user skill roots, catalogs, active guidance, and the curated payload;
- the installer exact-cleans only ~/.codex/skills/consolidate in addition to its already approved retired targets, with selected/deselected, absent, file, directory, reparse-point, sibling-preservation, failure-reporting, and repeated-repair behavior;
- active skills contain no Skill(...) or Read(...) pseudo-handoffs;
- active skills contain no declared calls to gh_delete, gh_set_value, or gh_query;
- design and plan explicitly prohibit stage-time mutation, even when a plan describes future gh_edit operations;
- execute requires fresh snapshot and epoch validation, partial-success accounting, and execution ownership;
- no stage requires unconditional global gh_canvas_cleanup;
- unfamiliar component identity and ports are grounded in live gh_library and gh_batch_component_info evidence;
- hidden-tool guidance uses the supported progressive-discovery path;
- the compact Wasp admission contract exists and the stale executable recipe files do not; and
- successful execution has no consolidate dependency.

The suite should use small exact assertions over the governed skill and guidance files. It must not parse arbitrary prose into a new policy language or freeze every word of the skills.

## Ephemeral acceptance scenarios

Before editing any skill, run all five scenarios once against the current skill assets and capture their routes, tool attempts, mutations, and terminal outcomes as the RED baseline. Replay the same prompts and scenario fixtures unchanged against the candidate skills and record the GREEN comparison. Do not repair a failing baseline by weakening or rewriting the scenario between runs. Keep this as PR evidence rather than adding a permanent scenario framework.

1. **Clear brief:** a bounded native Grasshopper request routes directly to execution, performs current schema/port preflight, mutates only owned state, and verifies the result.
2. **Ambiguous brief:** design remains read-only, surfaces the material decisions, and waits for the user's choice before routing onward.
3. **High-risk work:** an existing-canvas or destructive request produces an optional plan with a structural baseline and reaches execution only after the required approval.
4. **Missing Wasp:** live admission fails and both Rhino and Grasshopper mutation counts remain zero.
5. **Successful execution:** execution completes and reports success without invoking or requiring consolidate.

Each scenario records the invoked skills and tools, mutation boundary, and terminal outcome. Mocked tool transcripts are sufficient for the ambiguous, high-risk, missing-Wasp, and no-consolidation cases.

After installing the private candidate, run the clear-brief case once as a bounded disposable live Codex-lean scenario. It must use progressive discovery to reach at least one hidden admitted tool, create or change only harness-owned Grasshopper state, verify the result, and remove only that owned state during cleanup. Use a fresh disposable document or an equivalently isolated harness-owned boundary; do not expose a user document to the regression scenario. A mocked transcript cannot replace this installed lean-profile proof.

## Rollout gates

### Gate 1: private implementation and acceptance

Implement the private skill, guidance, exact installer cleanup, and focused contracts in Rook. Install the private candidate, replay the scenario suite, and complete the disposable live Codex-lean proof. Once the private acceptance criteria pass, the private PR may merge without waiting for public-repository work.

### Gate 2: public promotion

After Gate 1, create a separate rook-release promotion from the accepted private commit. Update only the corresponding public skills, hook, catalog, and product pages, then run the public repository's focused surface checks. The promotion PR does not reopen the private architecture or alter its accepted commit. Overall release readiness requires the applicable public promotion, but private acceptance and merge do not.

## Private acceptance

Implementation is accepted when:

1. The focused cascade contract suite and exact installer migration tests pass.
2. The five ephemeral scenarios satisfy their routing and mutation boundaries.
3. The retained private skill mirrors have exact recursive file-set and byte equality.
4. Install and repair remove the exact stale Codex consolidate target while preserving sibling Codex and Claude skills.
5. A clear bounded execution can complete without a design artifact, plan artifact, or consolidation step.
6. No production consolidation, DSPy, native C++, managed Rhino, bridge, compatibility-dispatch, MCP profile, or unrelated knowledge implementation changes are present.

The repository-wide suite is not required for this skill-surface correction. Any unexpected failure in the focused gates stops acceptance; unrelated defects are recorded separately rather than absorbed into this work.

## Expected implementation boundary

The coordinated implementation plan contains the two sequential rollout gates. The private implementation PR may change only:

- the three retained private skill roots and their active references;
- the two private consolidate skill roots being deleted;
- installer Codex skill mirrors;
- active private cascade guidance and post-install guidance;
- the existing exact retired-Codex-skill cleanup inventory and focused tests;
- one focused cascade contract test suite.

The separate public promotion PR may change only the corresponding rook-release skill, hook, catalog, product-page, and focused public surface-contract files.

A description-only correction may remove any remaining claim that gh_edit is transactional, but gh_edit behavior is not changed.

No runtime router, generalized selector or cleanup framework, tool-profile change, MCP capability deletion, internal dispatcher purge, Wasp implementation, dependency change, native change, managed-host change, or adjacent knowledge-system refactor belongs in this work.
