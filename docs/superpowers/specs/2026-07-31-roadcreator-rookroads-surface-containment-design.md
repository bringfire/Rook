# RoadCreator/RookRoads Surface Containment Design

- **Status:** Approved
- **Date:** 2026-07-31
- **Roadmap:** [Rook release surface hardening roadmap](../../roadmaps/2026-07-31-release-surface-hardening-roadmap.md)
- **Implementation base:** `c7687554ceba29be8cf559cb3244cce0d56d6fd1`

## Decision

RoadCreator and RookRoads are unsupported by the default Rook product. Rook will contain
their user-facing and agent-facing surfaces so users and agents do not see or
accidentally invoke them.

This is a surface-containment change, not an implementation purge. Dormant RoadCreator
and RookRoads schemas, handlers, `/rc/*` routes, adapters, bridge compatibility, and
native code remain when the admitted product cannot discover or dispatch them.

The private change ships as one coherent release-surface pull request. That boundary
does not require one commit and does not make installer or runtime operations
transactional. It means containment, skill removal, active-guidance correction,
migration cleanup, and their guards are reviewed and released together.

Wasp is outside this containment change. The six retired road-skill directories are
deleted in full, including two road-owned scaffold files that mention Wasp. No retained
Wasp product asset outside those retired roots is modified or deleted.

## Goals

- Pin the current 40 `rc_*` tool schemas as suspended lifecycle entries.
- Reserve the `rc_*` namespace centrally so a future name is neither advertised nor
  dispatchable without an explicit lifecycle decision.
- Remove all `rc_*` memberships from active profiles, allowlists, targeting policy, and
  model-facing tool groups.
- Remove the `design-road` and `masterplan-roads` skills from shipped Claude and Codex
  surfaces.
- Remove the four retired identities from scoped active user and agent guidance.
- Deny direct or internally mediated `rc_*` invocation before arguments are read or a
  downstream handler is selected.
- Remove the two retired Rook-owned Codex skill paths during every install and repair,
  independently of Codex component selection.
- Preserve native `road_intersection_*` tools and retained Wasp content without
  behavioral changes.
- Use Rook's existing lifecycle admission/filtering path and focused guards.

## Non-goals

- Deleting RoadCreator/RookRoads schemas, handlers, adapters, or `/rc/*` route strings.
- Refactoring `mcp_server/src/rook/bridge.py` or its compatibility discovery records.
- Removing RoadCreator-aware code from `src/RookNative`.
- Changing native `road_intersection_candidates` or `road_intersection_resolve`.
- Removing bundled road-profile knowledge or native road geometry behavior.
- Extracting or relocating the road-owned Wasp scaffold files from retired skills.
- Removing, rewriting, or permanently hash-pinning retained Wasp content.
- Cleaning historical specifications, plans, reports, probes, or postmortems.
- Adding permanent unsupported notices to active guidance.
- Creating a feature flag, extension framework, migration service, generalized
  filesystem-cleanup framework, or generalized plugin-support system.
- Admitting adjacent cleanup or refactoring into the containment pull request.

## Approaches considered

### 1. Existing lifecycle containment plus surface removal — selected

Add the exact current `rc_*` names to Rook's lifecycle registry, reserve the namespace
through the same central admission path, remove active memberships, delete the two
shipped skills from all three payload roots, correct active claims, and perform the
exact-path installer migration.

This is the smallest change that hides and blocks the unsupported surface while leaving
dormant implementation available in Git and source.

### 2. Hide the tools only from profiles and catalogs — rejected

Catalog-only hiding can leave known names directly invocable and does not protect a
future `rc_*` schema from accidental admission. It does not meet the execution-safety
requirement.

### 3. Delete every RoadCreator-related implementation — rejected

An implementation purge would touch bridge discovery, native delegation, compatibility
parsers, developer tooling, and broad tests without improving the admitted release
surface. It expands regression risk and violates the KISS boundary.

## Current exposed surface

At the implementation base, the active surface includes:

- 40 raw `rc_*` tool schemas in `mcp_server/src/rook/server.py`;
- `rc_*` memberships in active profiles or allowlists, targeting policy, and the
  `road_design` model-facing tool group;
- public and progressive list/search/read/call access to those schemas;
- internal agent dispatcher mappings;
- `design-road` and `masterplan-roads` under `.agents/skills`, `.claude/skills`, and the
  curated installer Codex payload;
- a Claude session-start instruction that selects `/design-road`;
- RoadCreator/RookRoads claims in active README, quick-start, agent-setup, post-install,
  and shipped skill-catalog guidance; and
- public plugin and product-site claims promoted separately through `rook-release`.

Dormant adapter, bridge, native, compatibility, developer, and historical references
are not removal targets.

## Runtime containment contract

### Pinned raw schema inventory

The raw schema source is inspected before lifecycle filtering. Its `rc_*` inventory is
exactly these 40 names:

```text
rc_apply_intersection_ownership
rc_apply_sidewalk_ownership
rc_assemble_route
rc_build_profile
rc_clothoid
rc_concrete_barrier_profile
rc_contour_levels
rc_cross_section
rc_crossing
rc_crossing_params
rc_cubic_parabola
rc_deltablok_profile
rc_extract_offsets
rc_get_road_profile
rc_guardrail
rc_guardrail_profile
rc_list_road_profiles
rc_longitudinal_profile
rc_ping
rc_pole_spacing
rc_project_offset_profile
rc_resolve_edges
rc_road_3d
rc_road_footprint
rc_roads
rc_roundabout_params
rc_sidewalk
rc_sidewalk_corners
rc_sidewalk_profile
rc_slope_profile
rc_slopes
rc_standards
rc_store_road_profile
rc_terrain_profile
rc_validate_profile
rc_validate_road_profile
rc_validate_style_set
rc_verge_profile
rc_vertical_curve
rc_widening
```

Every pinned name receives an exact lifecycle entry with the existing `suspended`
disposition and a shared unsupported-integration recovery message.

### Central namespace reservation

The existing lifecycle admission/filtering path remains the one authority for catalogs
and dispatch. It gains one narrow `rc_*` namespace rule rather than scattering prefix
checks across ingress points:

- a known pinned name resolves to its normal suspended lifecycle entry;
- an unknown `rc_*` name resolves to one bounded, non-retryable, fail-closed namespace
  denial; and
- a non-`rc_*` name follows existing lifecycle behavior unchanged.

Because public MCP, progressive meta-tools, server dispatch, Rook agent, Rook chat, plan
graph, tool dispatcher, and internal handlers already use that central decision, both
known and future `rc_*` names are denied before argument access or downstream dispatch.
Catalog projection, capability indexes, caches, progressive search, and progressive read
use the same central decision and cannot advertise either class of name.

The prefix reservation is an admission policy, not a filesystem glob and not a plugin
framework. A raw-schema contract test forces any future `rc_*` addition, deletion, or
rename to make an explicit lifecycle and pinned-inventory decision.

All exact `rc_*` memberships are removed from every active profile, full-profile set,
allowlist, targeting set, and model-facing group. The `road_design` group is removed if
empty. Dormant schemas, handler cases, dispatcher route mappings, `/rc/*` routing, bridge
discovery, compatibility records, and adapters remain.

Native `road_intersection_candidates` and `road_intersection_resolve` do not use the
reserved namespace. They remain advertised, readable, and dispatchable to their normal
routing boundary.

## Skills, guidance, and Wasp ownership

Delete exactly these six shipped skill roots and all contents beneath them:

- `.agents/skills/design-road`
- `.agents/skills/masterplan-roads`
- `.claude/skills/design-road`
- `.claude/skills/masterplan-roads`
- `installer/agent-assets/codex-skills/design-road`
- `installer/agent-assets/codex-skills/masterplan-roads`

Remove these four exact retired identities from scoped active user/agent guidance and
shipped catalogs:

- `design-road`
- `masterplan-roads`
- `RoadCreator`
- `RookRoads`

The active scope includes `README.md`, `QUICK_START.md`, `AGENT_SETUP.md`, Claude and
Codex post-install guidance, `scripts/session-start.sh`, and shipped skill listings,
counts, and catalogs. Guards use the four exact identities rather than generic words
such as `road`, so native road tooling and unrelated documentation remain valid.

Historical evidence is neither scanned nor rewritten. Active guidance does not become a
cemetery of unsupported notices. The names may remain only in migration code and focused
tests, this specification and its roadmap, historical documents, and the one-time public
release note.

Two Wasp-bearing road scaffold files disappear with their retired parent skills. They
are not extracted or relocated. For the private pull request, the retained Wasp product
path/hash inventory in skill/reference roots is derived from the pinned implementation
base after excluding the six retired roots and compared with the candidate tree. The
result is PR evidence, not a permanent hash contract. The governing specification and
roadmap are control documents rather than Wasp payload. A lightweight permanent guard
only proves that the general retained Wasp skill/reference roots still exist outside the
retired road roots.

## Installer migration

Retired Codex skill cleanup is a product migration, not a Codex component installation
action. One small migration-specific helper runs on every install and repair before
component-specific skill copying.

The helper resolves the current user's canonical `~/.codex/skills` parent once. It then
constructs exactly two lexical child paths:

- `~/.codex/skills/design-road`
- `~/.codex/skills/masterplan-roads`

For each target, it verifies that the lexical parent is the canonical skills root and
that the final name is the expected constant. It never resolves the target before
classification, enumerates the parent, uses a glob or prefix match, deletes a parent, or
touches Claude and sibling Codex skills.

Target classification uses non-following metadata such as `lstat` and the Windows
reparse attribute:

- an absent target reports `absent`;
- an ordinary directory is removed recursively and reports `removed_directory`;
- a symlink, junction, or other reparse point is unlinked without traversing its
  destination and reports `unlinked_reparse_point`;
- a regular file is unlinked and reports `removed_file`; and
- a bounded per-target exception reports `failed`.

Targets are handled independently and cleanup is idempotent. A failure is clearly
reported in installer output and the install summary as incomplete retired-skill
containment, while the other target and the remaining supported-skill installation
continue. Codex selection controls what is subsequently installed; it does not preserve
retired Rook-owned artifacts.

The installer-staged `.agents/skills` directory continues to be replaced by existing
installer cleanup, so removed skills cannot remain in the application payload.

## Verification

### Permanent automated contracts

- The raw, pre-lifecycle schema inventory equals the pinned 40-name set.
- Every pinned name has a `suspended` lifecycle entry.
- A synthetic `rc_future_probe` is hidden and centrally denied before argument or
  handler access.
- Active profiles, allowlists, targeting sets, and model-facing groups contain no
  `rc_*` membership.
- Public lists and progressive search/read/catalog projections expose no `rc_*` name or
  schema.
- Direct public, progressive, server, agent, chat, plan-graph, dispatcher, and internal
  calls deny known and synthetic `rc_*` names before touching untouchable arguments or
  downstream dispatch.
- `road_intersection_candidates` and `road_intersection_resolve` remain listed,
  readable, and dispatchable to their normal mocked routing boundaries.
- One authoritative profile-count contract records full `382`, full with the three
  deprecated tools `385`, readonly `120`, and lean `20`. Unrelated documents do not
  duplicate those assertions.
- The six shipped road-skill roots are absent.
- Scoped active guidance and shipped catalogs contain none of the four exact retired
  identities.
- Installer tests cover Codex selected and deselected, exact removal, sibling and Claude
  preservation, repeated repair, ordinary files and directories, non-following link or
  junction removal, independent failure, bounded outcomes, and incomplete-containment
  summary reporting.
- Lightweight Wasp guards prove the retained general skill/reference roots exist outside
  the retired road roots.

### Pull-request acceptance evidence

- From base `c7687554ceba29be8cf559cb3244cce0d56d6fd1`, derive the retained Wasp
  product path/hash inventory in skill/reference roots after excluding the six retired
  roots; compare it with the candidate tree and record a clean result without adding a
  permanent hash fixture.
- Confirm no diff in dedicated dormant implementation files. For mixed-ownership files,
  compare the dormant `rc_*` schema and dispatch blocks rather than requiring the entire
  file to be unchanged; required active agent-facing description edits remain allowed.
- Confirm no diff under `src/RookNative`, retained Wasp files, bundled road-profile
  knowledge, bridge compatibility, adapters, or historical documents.
- Run the complete Python MCP suite and installer/release guard tests.
- Build the Python wheel and installer payload and inspect staged Claude and Codex skill
  inventories.
- Start the installed MCP server and prove representative `rc_*` list/search/read/call
  containment and full-list absence.
- In the installed smoke, prove both native intersection tools remain listed, readable,
  and dispatchable to their normal routing boundary. Live Rhino geometry execution is
  not required because native code is unchanged and mocked dispatch tests protect the
  boundary.

## Commit and rollout boundaries

Implementation belongs in one coherent private containment pull request. Production
changes, skill deletions, active-guidance corrections, installer migration, and focused
guards ship together, but may use multiple reviewable commits. No claim of transactional
runtime or installer behavior is implied.

The pull request does not admit an implementation purge, adjacent refactor, native-code
change, Wasp rewrite, bundled-profile cleanup, bridge-compatibility cleanup, or
historical-document cleanup. Any claimed need to cross those boundaries stops for review
instead of expanding scope.

After private containment is accepted, `rook-release` receives a separate promotion
pull request that removes corresponding public product claims and adds a one-time
release note explaining that the previously advertised integration and skills are no
longer included.
