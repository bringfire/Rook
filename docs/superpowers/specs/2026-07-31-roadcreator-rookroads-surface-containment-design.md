# RoadCreator/RookRoads Surface Containment Design

- **Status:** Proposed for review
- **Date:** 2026-07-31
- **Roadmap:** [Rook release surface hardening roadmap](../../roadmaps/2026-07-31-release-surface-hardening-roadmap.md)
- **Baseline:** `90242fa4f09abf8f3b8ec994044787b61e77b446`

## Decision

RoadCreator and RookRoads are unsupported by the default Rook product. Rook will contain
their user-facing and agent-facing surfaces so users and agents do not see or
accidentally invoke them.

This is a surface-containment change, not an implementation purge. Dormant RoadCreator
and RookRoads adapter, bridge, targeting, native, compatibility, test-fixture, and
historical code may remain when the admitted product cannot discover or dispatch it.

Wasp is explicitly outside this containment change. Its skills, references, knowledge,
and Grasshopper workflows remain intact while a separate optional-integration audit is
considered.

## Goals

- Remove the `design-road` and `masterplan-roads` skills from shipped Claude and Codex
  surfaces.
- Remove RoadCreator/RookRoads instructions and capability claims from active user and
  agent guidance.
- Omit all current `rc_*` tools from public MCP tool lists, profiles, progressive
  discovery, and model-visible agent catalogs.
- Deny direct or internally mediated `rc_*` MCP invocation before arguments are read or
  downstream handlers are called.
- Clean the two retired Rook-owned Codex skill directories during installer upgrade.
- Preserve native `road_intersection_*` tools and Wasp without behavioral changes.
- Accomplish containment through Rook's existing lifecycle mechanism and focused guards.

## Non-goals

- Deleting RoadCreator/RookRoads adapter implementations or `/rc/*` route strings.
- Refactoring `mcp_server/src/rook/bridge.py` or its compatibility discovery records.
- Removing RoadCreator-aware code from `src/RookNative`.
- Changing native `road_intersection_candidates` or `road_intersection_resolve`.
- Removing bundled road-profile knowledge or native road geometry behavior.
- Removing or rewriting Wasp content.
- Cleaning historical specifications, plans, reports, probes, or postmortems.
- Creating a feature flag, extension framework, migration service, or generalized plugin
  support system.

## Approaches considered

### 1. Existing lifecycle containment plus skill removal — selected

Add the current `rc_*` names to Rook's lifecycle-containment registry, remove their
active profile/group/targeting memberships, delete the two shipped skills, and remove
active claims. The existing containment layer already filters public catalogs,
progressive disclosure, agent registries, and execution seams.

This is the smallest change that both hides and blocks the unsupported surface while
leaving dormant implementation available in Git and source.

### 2. Hide the tools only from the default profile — rejected

Profile-only hiding would leave the tools visible through the full profile and
progressive catalog and would not reliably block direct calls. It does not meet the
requirement that agents cannot mistakenly invoke the surface.

### 3. Delete every RoadCreator-related implementation — rejected

This would touch bridge discovery, native intersection delegation, compatibility
parsers, developer tooling, and broad tests without improving the user-facing
containment result. It creates unnecessary regression risk and violates the KISS scope.

## Current exposed surface

At the baseline, the active surface includes:

- 40 `rc_*` tool schemas in `mcp_server/src/rook/server.py`;
- `rc_*` memberships in full profiles, targeting policy, and agent tool groups;
- progressive search/read/call access to those tool schemas;
- internal agent dispatcher mappings;
- `design-road` and `masterplan-roads` in `.agents/skills`, `.claude/skills`, and the
  curated installer Codex payload;
- a Claude session-start instruction that automatically selects `/design-road`;
- RoadCreator/RookRoads claims in active README, quick-start, agent-setup, and
  post-install guidance; and
- public plugin skills and product-site claims that are promoted separately through the
  `rook-release` repository.

The source also contains dormant adapter, bridge, native, compatibility, developer, and
historical references. Those are not removal targets under this design.

## Containment contract

### MCP lifecycle

The 40 names present at the baseline are added as exact lifecycle entries with one shared
unsupported-integration recovery message. They use the existing `suspended` disposition:
the implementation remains in source, but it is not admitted to the product surface.

The existing lifecycle path remains authoritative:

- `_all_live_tools` omits contained names before public `list_tools` projection;
- capability indexes, caches, progressive search, and progressive read omit them;
- public MCP, progressive call, server dispatch, Rook agent, Rook chat, plan graph,
  tool dispatcher, and internal handlers deny them before argument access or downstream
  work; and
- containment denial remains bounded, non-retryable, and telemetry-compatible.

No new wildcard or plugin framework is introduced. The exact tombstone list is pinned by
tests. A guard separately prohibits any advertised or dispatchable `rc_*` name, so a
future addition cannot silently escape containment.

Active `rc_*` memberships are removed from MCP profiles, targeting sets, and model-facing
tool groups. Dormant schemas, handler cases, dispatcher mappings, `/rc/*` routing, and
bridge discovery may remain because lifecycle denial prevents admitted execution.

Native `road_intersection_candidates` and `road_intersection_resolve` do not use the
`rc_*` namespace and remain admitted without contract changes.

### Skills and guidance

Delete the following shipped skill directories:

- `.agents/skills/design-road`
- `.agents/skills/masterplan-roads`
- `.claude/skills/design-road`
- `.claude/skills/masterplan-roads`
- `installer/agent-assets/codex-skills/design-road`
- `installer/agent-assets/codex-skills/masterplan-roads`

Remove `/design-road`, `/masterplan-roads`, RoadCreator, and RookRoads capability claims
from active user/agent documents, post-install guidance, and the session-start hook.
Where active documentation still describes native road-intersection tools, it must call
them native Rook tools and must not imply RoadCreator availability.

Historical evidence remains unchanged. Public `rook-release` cleanup is a subsequent
promotion change built from the contained private source; it does not justify delaying
private containment.

### Upgrade cleanup

The Windows post-install step removes only these exact Rook-owned Codex destinations:

- `~/.codex/skills/design-road`
- `~/.codex/skills/masterplan-roads`

It does not enumerate or recursively clean the parent skill directory, does not match
wildcards, and does not touch sibling user skills. Cleanup failure is reported as a
warning and does not corrupt the remaining skill installation.

The installer-staged `.agents/skills` directory continues to be replaced by the existing
installer cleanup, so removed skills cannot remain in the application payload.

## Verification

### Automated contract tests

- Every baseline `rc_*` name resolves to the lifecycle-containment registry.
- Public tool lists for full, lean, and readonly profiles contain no `rc_*` name or
  RoadCreator/RookRoads text.
- Progressive search and read do not reveal `rc_*` names or schemas.
- Direct public, progressive, server, agent, chat, plan-graph, dispatcher, and internal
  calls return lifecycle denial before touching arguments or handlers.
- Profiles, targeting sets, and model-facing tool groups contain no admitted `rc_*`
  membership.
- Native `road_intersection_candidates` and `road_intersection_resolve` remain admitted.
- The six shipped road-skill directories are absent.
- Active user/agent guidance and session hooks contain no RoadCreator/RookRoads capability
  claim.
- Wasp skill/reference inventories are byte-identical before and after this change.
- Installer upgrade cleanup removes only the two exact retired Codex skill directories
  and preserves unrelated sibling skills.
- The default advertised tool count decreases by exactly 40 relative to the pinned
  baseline; generated counts and release assertions are updated accordingly.

### Product checks

- Run the complete Python MCP test suite.
- Run installer/release guard tests.
- Build the Python wheel and installer payload used by local testing.
- Inspect the staged Claude and Codex skill inventories.
- Start the installed MCP server and verify list/search/read/call containment for one
  representative `rc_*` name plus full-list absence.
- Verify both native road-intersection tools remain discoverable.
- No Rhino or RoadCreator host is required because this change does not alter or admit
  downstream RoadCreator execution.

## Commit and rollout boundaries

Implementation should be one focused containment branch. Production changes, skill
deletions, active guidance corrections, upgrade cleanup, and containment tests belong in
the same reviewed pull request so no intermediate release advertises an invocable but
unsupported surface.

The PR must not modify `src/RookNative`, Wasp files, bundled road-profile knowledge,
RoadCreator bridge compatibility, or historical documentation. Any claimed need to
cross those boundaries stops the implementation for review rather than expanding scope.

The public `rook-release` repository is updated through its normal separate promotion PR
after private containment is accepted.
