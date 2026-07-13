# Director MCP Surface Retirement Design

Date: 2026-07-13
Status: Approved direction; runtime implementation pending

## Decision

Retire the complete Rook Director MCP surface before deciding how much of the
underlying Director implementation should be deleted.

After this slice, an MCP client must not be able to discover, progressively
load, target, or invoke a `rhino_director_*` tool. The Python Director modules,
native Director routes, managed CanvasDirector bridge, tests of retained
non-MCP implementation, and historical design evidence remain in place for a
separate salvage-and-deletion review.

This is a product retirement, not a hidden experimental profile. No environment
flag, profile, alias, or meta-tool may restore the Director MCP tools.

## Product Boundary

Rook v1 remains the stable Rhino and Grasshopper capability prototype. It will
not continue evolving Director's Grasshopper-driven authoring, live Rhino
preview, snapshot, or export architecture.

Future scene preview, timeline, rendering, and finalized-video export work
belongs in RookStudio. The `rook2` Rhino floor may eventually provide a narrow,
receipt-bearing scene-export capability, but it must not absorb media
orchestration or the Director runtime.

No Director code is copied into `rook2` or RookStudio as part of this slice.

## Retired Tool Set

The following 18 tools are removed from the MCP contract:

1. `rhino_director_run`
2. `rhino_director_curve_samples`
3. `rhino_director_assemble_video`
4. `rhino_director_publish_video`
5. `rhino_director_canvas_extract`
6. `rhino_director_replay`
7. `rhino_director_replay_cancel`
8. `rhino_director_compile_motion`
9. `rhino_director_package_take`
10. `rhino_director_prepare_take`
11. `rhino_director_compile_take`
12. `rhino_director_worker_play`
13. `rhino_director_capture_take`
14. `rhino_director_preview_motion`
15. `rhino_director_capture_source_occurrence_v2`
16. `rhino_director_build_actor_set_from_source_occurrence_v2`
17. `rhino_director_write_actor_metadata_v2`
18. `rhino_director_read_actor_metadata_v2`

The already-unadvertised migration helper
`rhino_director_migrate_actor_metadata_v2` remains unadvertised and
uninvokable.

## MCP Contract Changes

### Tool discovery

`list_tools()` returns no name beginning with `rhino_director_` under any
supported tool profile. Canonical tool counts and architecture documentation
are updated from measured post-change values rather than hand-derived guesses.

The serialized discovery contract is broader than tool names. The complete
serialized `list_tools()` payload under every supported profile must contain
none of these obsolete Director discovery tokens:

- `rhino_director_`;
- `/director`;
- `RookVisionDirector` or `VisionDirector`; or
- `director` as a suggested `rook_tools_*` catalog path or domain.

Generic prose uses of the word "director" outside MCP catalog guidance are not
part of this guard. The four always-advertised `rook_tools_*` descriptions and
schemas are scrubbed of Director paths, domains, examples, and exact tool
names.

### Direct dispatch

The Director cases are removed from `_call_tool_dispatch()`. `call_tool()` adds
a narrow Director-prefix retirement guard. The order is:

1. normalize arguments;
2. resolve the active profile;
3. apply the existing readonly default-deny profile wall;
4. reject any name beginning with `rhino_director_` as the canonical unknown
   tool; and then
5. continue existing meta-tool, deprecated-tool, panel, targeting, discovery,
   and dispatch behavior for all other names.

This deliberately preserves readonly non-enumeration. Under `readonly`, a
guessed retired or otherwise unknown mutating name returns
`tool_profile_blocked`, exactly as before. Under `full` and `lean`, every
`rhino_director_*` name returns the canonical unknown-tool response before
panel policy, Rhino targeting, session/port validation, discovery, or dispatch.
The prefix guard covers the 18 inventoried tools, the already-unadvertised
migration helper, and any stale or newly guessed Director alias.

Arbitrary non-Director unknown names retain their existing behavior. This slice
does not introduce a general dispatch-membership guard or change the server's
global unknown-tool contract.

The retirement guard is an explicit negative product boundary, not a complete
dispatch registry. It must not depend on `_DISPATCHABLE_TOOL_NAMES`, the
capability index, `inspect.getsource()`, Rhino discovery, or any asynchronous
lookup.

`_DISPATCHABLE_TOOL_NAMES` remains best-effort capability metadata. Its existing
source-inspection failure fallback to `META_TOOL_NAMES` must not participate in
direct dispatch admission. A scanner failure may degrade progressive catalog
metadata, but it must never turn the server into a silent four-tool runtime.

Retirement must not return a Director-specific migration or deprecation
response that could become another lasting compatibility surface.

### Progressive disclosure

Director groups and entries are removed from the agent tool groups,
progressive-disclosure always-include sets, lightweight catalogs, and direct
tool-dispatch tables. The `rook_tools_*` meta-tools must not reveal or load a
retired Director tool.

The existing `rook_tools_call` target-ordering rule remains unchanged: under a
readonly profile it may return `tool_profile_blocked` before revealing whether
an arbitrary target exists; under `full` or `lean` a retired Director target is
`not_mcp_dispatchable`. In every profile it must stop before `call_tool()`,
targeting, or Director implementation. Direct MCP calls follow the separate
profile-wall-then-retirement-guard order above; the intentionally scoped
meta-dispatcher retains its existing target enumeration policy.

### Targeting and capability metadata

Director names are removed from MCP targeting classifications and capability
indexes where those structures describe callable tools. Generic prefix logic
may remain only when it cannot synthesize or expose a callable Director entry.

### Internal agent execution surface

The in-process agent `ToolDispatcher` is a separate execution surface from the
MCP `call_tool()` handler. Its direct `rhino_director_curve_samples` bridge
route is removed, as are the `director` and `director_readonly` agent tool
groups and any capability-inventory records derived from them. An internal
agent must not recover a retired Director operation merely because the native
`/director/*` routes remain installed.

CanvasDirector template and implementation modules may retain dormant internal
data, including historical artifact fields, until the next disposition pass.
They must not be imported into an active agent catalog or exposed through an
MCP tool, group, profile, meta-tool, or current user instruction.

### Documentation and installed guidance surface

The implementation audit covers current README/quick-start/architecture,
troubleshooting, installer-provided agent assets, skills, hooks, and active work
queues in addition to Python registry code. Current guidance must not recommend
a retired Director tool, catalog path, or workflow. Dated evidence and
postmortems retain their historical content; an active-looking historical work
queue or gap analysis receives a visible supersession note rather than having
its evidence rewritten.

Four capability-contract documents require explicit, visible partial-
supersession notices because their profile and progressive-disclosure
architecture remains active while their Director examples are now invalid:

- `docs/superpowers/specs/2026-06-29-mcp-tool-exposure-profile-design.md`;
- `docs/superpowers/plans/2026-06-29-mcp-tool-exposure-profile.md`;
- `docs/superpowers/specs/2026-06-30-capability-index-progressive-disclosure-design.md`;
  and
- `docs/superpowers/plans/2026-06-30-capability-index-progressive-disclosure.md`.

Each notice appears immediately below the title/status preamble and links to
this retirement design. It states:

- the general profile or progressive-disclosure architecture remains active;
- all `rhino_director_*`, `/director`, VisionDirector, and Director-domain
  examples, allowlist entries, count assumptions, acceptance criteria, and
  positive dispatch tests are superseded as of 2026-07-13;
- those examples must be replaced with non-Director fixtures when maintaining
  or replaying the plan; and
- the document must not be used to restore a Director MCP tool.

The underlying historical content remains unchanged beneath the notice. This
partial-supersession pattern applies generally to any approved, ready,
current-status, or implementation-directive document found by the retirement
audit to contain actionable Director MCP instructions. Purely dated evidence,
completed live-gate records, and postmortems do not require a notice unless
they present themselves as current instructions.

Uninstall guards that preserve existing Director output artifacts remain in
place. Surface retirement does not authorize deleting user data.

## Explicitly Retained In This Slice

- Native `/director/*` routes and their handler implementations.
- Python `director*.py` and `canvas_director.py` implementation modules.
- The managed CanvasDirector extraction bridge.
- Native frame capture, display-mode handling, video assembly, and publishing
  infrastructure that may serve non-Director workflows.
- Pure motion, timeline, and camera-planning mathematics.
- Historical specs, plans, probes, and test evidence.
- Unit and integration tests that exercise retained implementation beneath the
  MCP boundary.

Keeping these items is temporary preservation for the next review, not a
commitment to their long-term architecture.

## Retained Public Media Sentinels

The following existing public tools form the deterministic regression set for
capabilities retained in this slice. Each must remain advertised in every
profile that advertised it before retirement, remain present in the static
dispatch set, and retain its pre-retirement profile/targeting policy:

### Video job surface

- `rhino_render_video`
- `rhino_video_status`
- `rhino_video_cancel`
- `rhino_video_result`
- `rhino_video_estimate`
- `rhino_video_jobs`
- `rhino_video_models`

### Viewport and display-mode surface

- `rhino_viewport`
- `rhino_capture_depth`
- `rhino_display_modes`
- `rhino_display_mode_set`

### Vision artifact surface

- `rhino_vision_artifacts`
- `rhino_vision_get_artifact`
- `rhino_vision_approve`
- `rhino_vision_delete_artifact`
- `rhino_vision_consume_approved`
- `rhino_vision_presentation`

This sentinel set does not claim that every implementation beneath these tools
is permanently retained. It prevents the MCP-surface retirement from
accidentally deleting independent media, capture, display, or artifact
capabilities before their own disposition review.

## Test Strategy

The old positive MCP-surface tests are replaced with retirement guards that
prove:

1. no `rhino_director_*` name appears in the full `list_tools()` result;
2. the fully serialized `list_tools()` payload under every supported profile
   contains no retired tool name, Director path, VisionDirector label, or
   Director catalog-domain guidance;
3. direct invocation of every retired name and an invented
   `rhino_director_future_probe` returns unknown tool under `full` and `lean`,
   and `tool_profile_blocked` under `readonly`, with no live Rhino instance and
   with conflicting `port`/`session` targeting arguments;
4. spies prove `full` and `lean` retired-name calls stop after the prefix guard
   without entering panel policy, Rhino discovery, target resolution,
   `_call_tool_dispatch()`, or any Director implementation; readonly calls stop
   at the existing profile wall without entering those later stages;
5. progressive-disclosure groups and catalogs contain no Director entry, and
   `rook_tools_call` cannot dispatch a retired name under any profile;
6. MCP targeting sets, agent groups, the internal agent `ToolDispatcher`, and
   active capability-inventory records contain no retired Director name or
   direct `/director/*` route;
7. forcing dispatch-case source inspection to fail, or substituting the
   four-meta-tool fallback set, does not prevent a known ordinary tool from
   reaching its normal profile/targeting/dispatch path;
8. current documentation and installed agent guidance contain no actionable
   retired Director instruction; the four named June 29/30 capability
   documents and any other approved/current actionable document carry visible
   partial-supersession notices, while historical evidence and user artifacts
   remain preserved;
9. every tool in **Retained Public Media Sentinels** remains advertised and
   dispatchable under its pre-retirement profiles; and
10. the broader MCP server, internal agent-dispatch, capability-index,
   targeting, and tool-profile suites remain green with the
   measured lower tool count.

Director module, compiler, package, worker, native-route, and capture tests are
not deleted merely because their MCP wrappers are retired. Their disposition
belongs to the next implementation review.

## Documentation Changes

User-facing and canonical architecture documentation must stop presenting
Director as an available MCP capability. Historical documents keep their dated
claims and receive supersession notes only where a reader could mistake them
for current instructions.

The measured post-change count is updated consistently in `AGENTS.md`,
`README.md`, `docs/CURRENT_ARCHITECTURE.md`, and
`docs/AGENT_ARCHITECTURE.md`. README feature copy that currently advertises
Director-based camera animation is removed or replaced with the retained
generic video-job capability. Active-looking Director entries in
`docs/rook_docs/work-queue.md` and the typed-route gap analysis receive a dated
retirement/supersession notice. The dated replay troubleshooting incident may
remain as historical operational evidence.

The four June 29/30 capability-profile and progressive-disclosure documents
listed above also receive their prescribed partial-supersession notices. Their
non-Director architecture remains canonical; only their Director fixtures,
counts, and acceptance instructions are retired.

The retirement record should state the new direction plainly:

- Rook v1 Director is no longer an MCP product surface.
- `rook2` remains a narrow Rhino connector and broker trunk.
- RookStudio is the intended owner of future Three.js preview, rendering, and
  video-export workflows.

## Failure And Rollback Posture

This slice makes no data migration and deletes no user artifacts. Existing
Director packages and `.rook` metadata remain on disk untouched.

If an unrelated regression is discovered, the implementation branch can be
reverted as a unit. Director tools must not be selectively re-enabled as a
shortcut; any proposed restoration requires a new explicit product decision.

## Acceptance Criteria

- No MCP discovery, profile, meta-tool, or dispatcher path exposes a
  `rhino_director_*` tool.
- The complete serialized tool-discovery payload contains no obsolete Director
  catalog guidance.
- Direct calls to all retired names and future names under the retired prefix
  preserve readonly default-deny behavior and otherwise fail as unknown before
  targeting, discovery, or dispatch, including with malformed or conflicting
  target arguments.
- Meta-dispatch calls cannot reveal or invoke a retired Director target and
  retain their existing profile-scoped enumeration semantics.
- Dispatch-case scanner failure cannot reduce the callable server to the four
  meta-tools.
- Internal agent groups, inventories, and direct dispatch cannot recover a
  retired Director operation.
- No native route, Director implementation module, or user artifact is removed
  in this slice.
- Every named retained public media sentinel preserves its discovery,
  dispatchability, profile, and targeting contract.
- Canonical tool counts are regenerated from the working server.
- Relevant MCP, profile, targeting, and documentation tests pass.
- The change is confined to Rook; `rook2` and RookStudio remain unchanged.

## Next Decision

After the surface is retired and verified, conduct a file-by-file Director
disposition pass:

- keep generic capture, video, and publishing infrastructure;
- extract only independently useful motion, camera, identity, or snapshot
  primitives;
- archive evidence and superseded contracts;
- delete Director-specific Grasshopper export, live replay, worker packaging,
  and migration machinery that no longer has a product consumer.
