# MCP Tool Exposure Profiles — Phase One Design

- **Status:** Design (awaiting user review)
- **Date:** 2026-06-29
- **Branch:** `worktree-codex+mcp-tool-exposure-profile` (off `main` @ `975970ef`, includes PR #380)
- **Campaign:** "MCP tool exposure profile" — separate from the LM5D local-worker campaign.

---

## 1. Problem

Rook's public MCP server exposes **every tool through one flat, unconditional `list_tools()`**
([`server.py:3125`](../../../mcp_server/src/rook/server.py)). Live `list_tools()` advertises **427
unique tools** by default (~360k JSON chars, ~90k tokens by char/4). (An AST scan finds **430** static
`Tool(...)` definitions; `list_tools()` gates out **3** deprecated-interactive tools —
`rhino_command_experiment`, `rhino_learn_next`, `rhino_prepare_geometry` — whenever
`_interactive_command_learning_enabled()` is false ([`server.py:13358`](../../../mcp_server/src/rook/server.py)),
which is the default. **The profile contract targets the live 427**; the 3 gated definitions are
separate dead-definition hygiene, out of scope for this campaign.) Clients that eagerly load all
MCP tool schemas into model context — OpenAI Codex (pre-deferral builds), Cursor, Windsurf — pay that
cost up front, with the documented consequences: context bloat, degraded tool selection, confusion
between nearby tools, broader exposure of mutating/specialized tools, and higher latency/cost.

Claude Code defers tool schemas natively (its own tool-search), so it is largely insulated. **The
principle this campaign establishes: Rook must not depend on the client being smart about tool
discovery.** Mitigation must work server-side, for the dumbest reasonable client.

### Research grounding (why static profiles, not a dynamic protocol)

A deep-research pass (2026-06-29) established:

- **The MCP spec offers no grouping/filtering primitive.** `tools/list` supports cursor pagination
  (transport help, not context reduction) and a `tools.listChanged` capability; tool annotations
  (`readOnlyHint`/`destructiveHint`/…) are explicitly **advisory hints, not enforcement**.
- **Both community standardization attempts were rejected** — SEP-1300 "Tool Filtering via Groups and
  Tags" (closed) and SEP-2084 "Primitive Grouping" (rejected by Core Maintainers, Feb 2026). No
  standard is imminent; server-side mitigation is the responsibility of the server.
- **Client-side deferral exists but cannot be depended on** — OpenAI `defer_loading` + `tool_search`
  and Anthropic's Tool Search Tool both defer schemas, but they are *client/API capabilities*. Codex's
  own `tool_search` has documented misses (exact-named deferred tools not surfaced). Rook should
  *benefit* from these when present, never *require* them.
- **The production-converged pattern is explicit, statically-selected toolsets/profiles**, configured
  out-of-band (env/flags/headers) — e.g. GitHub's `github-mcp-server` toolsets and read-only mode, and
  Buildkite's profile/read-only variants.

A fully dynamic meta-tool router (a `rook_call_tool`-style "2–3 tools execute everything" surface) is
explicitly **out of scope** for phase one: for clients that aren't smart, a meta-tool that advertises
"more tools exist" is unusable (the client never receives those schemas and cannot call them), and for
a mutation-heavy CAD/BIM domain it imposes a large validation/observability/safety burden. The
genuinely client-agnostic lever is a **smaller static `list_tools()`**. That is what we build.

---

## 2. Public contract

A single environment variable selects the exposure profile:

```
ROOK_MCP_TOOL_PROFILE = full | lean | readonly
```

Resolution is a **pure function** `resolve_profile(env) -> Profile` (unit-testable in isolation; the
MCP process fails fast *from its result* — env reads are not buried in side-effecting code):

| Env value        | Resolves to | Behavior |
|------------------|-------------|----------|
| *absent / unset* | `full`      | Current live `list_tools()` surface (**427** by default; see §1). **Existing installs never silently shrink.** |
| `full`           | `full`      | Current live `list_tools()` surface (**427** by default; see §1). |
| `lean`           | `lean`      | Minimal compatibility surface (§4). |
| `readonly`       | `readonly`  | Read-only surface + server-side enforcement (§5). |
| *any other value* | **error**  | **Hard configuration failure at startup** with a clear message. Never a silent fallback to `full`. |

**Internal model:** the resolver is shaped `domain × posture`, where phase one fixes `domain = all`
and varies `posture ∈ {full, lean, readonly}`. Domain slices (`grasshopper`, `rhino`, `bim`,
`vision`, `director`) are **reserved, not built** — they are the natural follow-up once telemetry
justifies them, and the data model must not preclude `domain=grasshopper × posture=readonly` later.

### Hard invariants

1. **Absent ⇒ `full`.** Backward compatibility is the default.
2. **Invalid ⇒ hard failure.** No silent fallback.
3. **`lean` is list-only; `readonly` is a wall.** (Named invariant — see §3.)
4. **`lean` is a minimal *compatibility* surface, not "the new preferred Rook surface."** The typed-route
   preference (CLAUDE.md) stands; `full` remains the deterministic typed palette.
5. **Public `readonly` is its own affirmative allowlist**, stricter than Rook's internal
   readonly-agent vocabulary, default-deny (§5).
6. **Existing configs are never rewritten** except by an explicit user-run migration/fix action.

---

## 3. The asymmetry invariant: "lean list-only / readonly wall"

`lean` and `readonly` exist for **different purposes**, and must enforce differently. This asymmetry is
intentional and **must not be "simplified" into a uniform wall.**

| Profile    | `list_tools()` returns | `call_tool()` guard |
|------------|------------------------|---------------------|
| `full`     | all 427 (live)         | unchanged |
| `lean`     | the 17 (§4)            | **unchanged** — lean is *advertisement-only* |
| `readonly` | the read-only set (§5) | **rejects mutators** — readonly is *enforcement* |

- **`lean` = context reduction**, a token concern, *not* access control. A discovery-naive client only
  calls what it sees; a client without a hidden tool's schema cannot form a valid call anyway. A wall
  there buys nothing and invents a new failure mode (valid tool, valid args, rejected) that harms
  hybrid/smart clients for zero safety gain. So `lean` touches **only `list_tools()`**.
- **`readonly` = safety.** It must be an enforced wall: mutators are hidden *and* rejected if a stale
  client calls one anyway. So `readonly` touches **both `list_tools()` and `call_tool()`**.

---

## 4. `lean` membership (pinned)

`lean` is a **minimal compatibility surface** for clients that would otherwise choke on 427 schemas.
Its job is "operate an already-running Rook/Rhino session," not "deliver the best typed-route UX"
(that is `full`). Membership is **pinned exactly** here and enforced by snapshot test:

```
rhino_ping
rhino_instances
rhino_sessions
rhino_session_capabilities
rhino_get_active_instance
rhino_set_active_instance
rhino_clear_active_instance
knowledge_query
rhino_knowledge_query
gh_knowledge_query
rhino_objects
rhino_geometry
gh_snapshot
gh_errors
gh_edit
rhino_execute_intent
gh_execute_intent
```

**17 tools.** Rationale for the shape:

- **Connection/session basics** (`rhino_ping`, instance/session introspection + binding) — connect and
  target an already-running Rhino.
- **Knowledge queries** (`knowledge_query`, `rhino_knowledge_query`, `gh_knowledge_query`) — discover
  what exists without loading 427 schemas.
- **Inspection** (`rhino_objects`, `rhino_geometry`, `gh_snapshot`, `gh_errors`) — see document and
  canvas state, read solved data and errors.
- **GH batch path** (`gh_snapshot` → `gh_edit`) — the *direct, preferred* GH workflow per CLAUDE.md.
- **NL reach** (`rhino_execute_intent`, `gh_execute_intent`) — reach anything not directly in the lean
  set via natural-language routing. In `lean`, the slower NL routers are the deliberate trade for a
  tiny surface; clients wanting the fast typed palette use `full`.

**`rhino_launch` is deliberately excluded.** Rook's MCP server only discovers an *already-running*
Rhino (RookNative writes the discovery file on plugin load); if Rhino is not up, `lean` has nothing to
talk to regardless, and `rhino_ping` already reports reachability. `rhino_launch` is a
recovery/bootstrap tool, not an operate-the-session tool. If we ever want `lean` to bootstrap Rhino
from nothing, that is a deliberate, separately-named scope expansion — not a default.

---

## 5. `readonly` membership and enforcement (safety boundary)

`readonly` is the safety boundary and is treated as a **contract**: an affirmative allowlist built by
**audit**, not intuition.

### 5.1 Source of truth

- New constant **`PUBLIC_READONLY_TOOL_NAMES`** — an affirmative allowlist of tools proven side-effect-free.
- **Not derived from internal `READONLY_ALLOWED_GROUPS`.** That internal set (≈87 tools) is tuned for
  RookChat readonly-agents and leaks tools unacceptable for a *public* safety boundary —
  `rhino_select*` (mutates selection), `rhino_layer_visibility` / `rhino_layer_lock` (mutate layer
  state), and possibly knowledge/session-mutating exploration tools. Public `readonly` must be
  **stricter**.

### 5.2 Default-deny

A tool is in `readonly` **only if explicitly listed**. Any tool not on the allowlist — including any
newly added tool — is treated as a mutator: **hidden from `list_tools()` and rejected in
`call_tool()`.** The conservative failure mode (unknown ⇒ mutator) is mandatory for a safety boundary.

### 5.3 Inclusion criteria (operationalized)

A tool qualifies for `PUBLIC_READONLY_TOOL_NAMES` **only if it does NONE of the following**:

1. Mutates the **Rhino document** (geometry create/modify/delete/transform/boolean/extrude/loft/…,
   layers, materials, blocks/instances, annotations, groups, user text, gumball).
2. Mutates the **Grasshopper canvas** (create/edit/delete/move/align/cluster/connect components, set
   values/scripts/pins, clear, bake, undo, references).
3. Mutates **Revit / RookBIM** state (select/export elements, set parameters).
4. Mutates **files or artifacts** (capture/register/export/download/render-to-file/export-with-manifest).
5. Triggers **provider/external/async jobs** (video, 2d-to-3d, render, speech, vision generation,
   director run/publish).
6. Mutates **knowledge or session** state (record/save/add/learn/reflect/evolve/consolidate/upgrade;
   start/end/note sessions or explorations; knowledge reload).
7. Mutates **UI selection / layer / viewport / display** state (select/deselect, layer
   visibility/lock/current, viewport/camera/zoom/focus, views save/restore, display mode, gumball).
8. Controls **agents / background work** (spawn/abort/answer agents, plan_and_execute).
9. Executes **arbitrary code/commands** that could mutate (`rhino_execute`, `rhino_command`,
   `run_library_script`, `rhino_execute_intent`, `gh_execute_intent`). *(`rhino_command_queue` only
   **reads** the prioritized learn-queue — it is in the readonly allowlist, §5.5, not here.)*

### 5.4 Named sentinel exclusions

These tools **must never** appear in `PUBLIC_READONLY_TOOL_NAMES`; a snapshot/assertion test pins their
exclusion explicitly, because they are the easy "not geometry-creation, therefore read-only" mistakes:

```
rhino_select  rhino_deselect  rhino_select_all  rhino_select_none  rhino_select_invert
rhino_select_by_name  rhino_select_by_type
rhino_layer_visibility  rhino_layer_lock  rhino_layer_current
gh_edit  gh_clear  gh_bake_output
rhino_create  rhino_transform  rhino_delete  rhino_boolean
capture_script_artifact  gh_add_pattern  knowledge_record
spawn_agent  plan_and_execute
rhino_execute  rhino_command  rhino_execute_intent  gh_execute_intent
```

(Provider-job tools, artifact/file mutators, and knowledge/session mutators are excluded as whole
families by §5.3 rules 4–6.)

### 5.5 The audited allowlist

**Provenance.** All **430** static tool definitions were classified default-deny by a temporary local
audit script (not committed; the reproducible classifier is a deliverable of the implementation — §8),
then every *inclusion* was adversarially re-verified by hand against §5.3/§5.4 (the only direction that
can leak a mutator). The audit produced 147 read-only candidates; hand-verification **demoted 2** whose
verbs imply a state transition the description cannot clear (see "Excluded by adversarial review" below).

**Result: `PUBLIC_READONLY_TOOL_NAMES` = 145 tools.** Over the **live 427-tool** surface (§1) the
arithmetic closes: `145 readonly + 282 excluded = 427`, where 282 excluded = **276 mutators** (279
audited minus the 3 deprecated-interactive definitions gated out of `list_tools()`) + **4 uncertain** +
**2 demoted**. Sentinel check (§5.4): no sentinel present in the allowlist. The list below is
authoritative; the code constant must equal it exactly and is pinned by the §8 snapshot test.

> Note: `PUBLIC_READONLY_TOOL_NAMES` is **not** a superset of `lean`. Five `lean` tools are mutators
> (`gh_edit`, `rhino_execute_intent`, `gh_execute_intent`, `rhino_set_active_instance`,
> `rhino_clear_active_instance`) — expected, because `lean` is a *context* surface that must do work,
> while `readonly` is a *safety* surface. The two profiles are orthogonal; both are subsets of `full`.

**Authoritative allowlist (alphabetical, 145).** The code constant `PUBLIC_READONLY_TOOL_NAMES` must
equal this set exactly; the §8 snapshot test pins it.

```
agent_status
gh_batch_component_info  gh_categories  gh_constraints  gh_errors  gh_get_reference
gh_inspect_output  gh_knowledge_query  gh_library  gh_migration_status  gh_pattern_links
gh_pattern_stats  gh_query_observations  gh_query_patterns  gh_selection  gh_session_current
gh_session_history  gh_snapshot  gh_status  gh_structure_query
gh_validate_latency  gh_validate_regression  gh_validate_scenarios
knowledge_query  metrics_summary  parse_command
rc_assemble_route  rc_build_profile  rc_clothoid  rc_concrete_barrier_profile  rc_contour_levels
rc_cross_section  rc_crossing_params  rc_cubic_parabola  rc_deltablok_profile  rc_extract_offsets
rc_get_road_profile  rc_guardrail_profile  rc_list_road_profiles  rc_ping  rc_pole_spacing
rc_project_offset_profile  rc_roads  rc_roundabout_params  rc_sidewalk_profile  rc_slope_profile
rc_standards  rc_terrain_profile  rc_validate_profile  rc_validate_road_profile  rc_validate_style_set
rc_verge_profile  rc_vertical_curve  rc_widening
rhino_2d_to_3d_jobs  rhino_2d_to_3d_models  rhino_2d_to_3d_result  rhino_2d_to_3d_status
rhino_analyze_prompt  rhino_artifacts
rhino_block_compare  rhino_block_find_instances  rhino_block_info  rhino_block_instances
rhino_block_layer_census  rhino_block_nested  rhino_block_objects_detailed  rhino_blocks
rhino_brep_edges  rhino_brep_faces  rhino_brep_vertices  rhino_closest_point
rhino_command_knowledge  rhino_command_observations  rhino_command_queue
rhino_curvature_curve  rhino_curvature_surface  rhino_curve_frame  rhino_curve_point_at
rhino_curve_tangent  rhino_declared_targets  rhino_director_curve_samples  rhino_display_modes
rhino_document  rhino_draft_angle  rhino_geometry  rhino_get_active_instance
rhino_gumball_history  rhino_gumball_status  rhino_instances  rhino_is_closed  rhino_is_valid
rhino_knowledge_query  rhino_layer_dependencies  rhino_layers  rhino_learning_progress
rhino_linetypes  rhino_materials
rhino_measure_area  rhino_measure_bbox  rhino_measure_centroid  rhino_measure_distance
rhino_measure_length  rhino_measure_volume  rhino_merge_contract_validate  rhino_objects
rhino_ping  rhino_planned_contracts  rhino_selection  rhino_session_capabilities  rhino_sessions
rhino_surface_normal  rhino_usertext_document_get  rhino_usertext_object_get  rhino_validate_export
rhino_video_estimate  rhino_video_jobs  rhino_video_models  rhino_video_result  rhino_video_status
rhino_views  rhino_vision_artifacts  rhino_vision_get_artifact  rhino_work_units  rhino_workbench_list
road_intersection_candidates
rookbim_active_document  rookbim_element_info  rookbim_element_parameters  rookbim_list_categories
rookbim_query_elements  rookbim_status
scene_bim_facts  scene_context  scene_graph  scene_object_semantic_context  scene_query
scene_relationship_evidence  scene_relationship_profile  scene_semantic_relationships  scene_stats
script_library_search  session_current  session_history  session_list
```

**Rationale by theme** (the code block above is authoritative; this explains the inclusion logic and
the boundary calls against mutating siblings — no per-theme counts, to avoid arithmetic drift):

- **Connection / session / instance:** status/list/get only. `rhino_set_active_instance` /
  `rhino_clear_active_instance` are *excluded* (mutate the target binding).
- **Knowledge / metrics / command queries:** read of stores; no record/save/reload. `parse_command`
  parses to structured params but **does not execute**; `rhino_analyze_prompt` analyses only;
  `script_library_search` is read discovery.
- **Grasshopper:** snapshot / errors / status / categories / library / inspect / query.
  `gh_selection` **reads** the canvas selection (vs `gh_edit`, `gh_clear`, `gh_set_reference` →
  mutators); the `gh_validate_*` trio benchmarks/analyses the pattern store and returns results without
  writing it.
- **Geometry analysis / measurement:** pure compute over existing geometry, no creation.
  `rhino_curve_ops` is *excluded* (edit multiplexer).
- **Document inventory / display / selection / user-text:** list / inspect / read-current-state.
  Excluded siblings: `rhino_views_save` / `_restore`, `rhino_display_mode_set`,
  `rhino_layer_visibility` / `_lock` / `_current`, `rhino_select*` / `rhino_deselect`,
  `rhino_usertext_*_set` / `_delete`, gumball activate/deactivate/settings. `rhino_layer_dependencies`
  *analyses* deletability (returns `canDelete`) without deleting.
- **Blocks:** inspect definitions/instances; every `rhino_block_set_*` / `_transform_*` / `_replace_*` /
  `_add`-`_remove_objects` / `_user_strings` → mutator.
- **Director / contracts / workbench / artifacts:** read-only inspection/validation
  (`rhino_director_curve_samples`, `rhino_declared_targets`, `rhino_planned_contracts`,
  `rhino_merge_contract_validate`, `rhino_validate_export`, `rhino_workbench_list`, `rhino_work_units`,
  `rhino_artifacts`). Excluded siblings: `*_declare` / `_activate` / `_execute` / `_launch` / `_close`.
- **Async jobs:** `*_jobs` / `_models` / `_status` / `_result` / `_estimate` read ledgers; `*_submit` /
  `_cancel` / `_remove_background`, `rhino_render_*` → mutators (rule 5).
- **Vision / RookBIM / Scene:** read artifacts / elements / already-projected facts. Excluded siblings:
  `rhino_vision_approve` / `_delete_artifact`, `rookbim_select_elements` / `_clear_selection` /
  `_export_*`, and the **critical scene split** — `scene_project_*` / `scene_refine_containment` /
  `scene_exact_neighbors` / `scene_classify` / `scene_overlay` mutate the graph, so only the
  read-of-projected-facts `scene_*` tools are included.
- **RoadCreator:** pure-compute profile/curve math + read/validate/list/get. Constructive verbs
  (`build` / `assemble` / `project`) are **pure functions returning data**; the RC tools that write
  geometry or store profiles (`rc_road_3d`, `rc_sidewalk`, `rc_store_road_profile`, `rc_apply_*`,
  `road_intersection_resolve`) → mutators.

#### Excluded by adversarial review (demoted from the audit's read-only bucket)

| Tool | Why excluded (default-deny) |
|------|------------------------------|
| `rhino_artifact_refresh` | "Re-check an artifact's file state… never touches the file" — never touches the *file*, but "refresh"/"re-check" updates the artifact registry's cached state: a state transition. |
| `rhino_vision_consume_approved` | Description: "the 2D→3D handoff **consumes** a concept image." Whether "consume" flips a consumed-flag is unclear from the text; ambiguity ⇒ exclude. |

Either may be **promoted** to `readonly` later **only** after handler-level confirmation it performs no
state write — a visible, tested decision, never a silent one.

#### Excluded as uncertain (audit `uncertain` bucket — stay excluded by default-deny)

`gh_extract_recipe`, `gh_reflect` (both return a `draft_id`; unclear whether the draft persists),
`rhino_command_interactive_prompt` (polls a live interactive-command subsystem — not a pure data read),
`rhino_director_replay` (drives a transient viewport animation). Same promotion rule applies.

### 5.6 Enforcement point

The readonly guard fires **early in `call_tool()`** — at approximately
[`server.py:20919`](../../../mcp_server/src/rook/server.py), immediately after argument normalization
and **before** both the deprecated-interactive branch (which records an observation) and
`targeting.policy_for_tool(name)` ([`server.py:20931`](../../../mcp_server/src/rook/server.py)). This
ensures a blocked call triggers **no targeting/session side effects, no route errors, and no
observation/knowledge recording** — it is a policy denial, not an execution.

Rejection envelope (rendered by `_format_tool_result()` as an MCP `"Error: {...}"` response):

```json
{ "success": false, "data": { "code": "tool_profile_blocked", "tool": "<name>", "profile": "readonly" } }
```

### 5.7 Annotations (later, courtesy only)

`readOnlyHint` / `destructiveHint` may later be generated **from** `PUBLIC_READONLY_TOOL_NAMES` as a
courtesy to smart hosts. The allowlist — not the annotation — is the load-bearing authority, consistent
with the spec's "annotations are advisory" stance.

---

## 6. Single source of truth (module)

- New module **`mcp_server/src/rook/mcp_tool_profiles.py`** holds: the `Profile` model,
  `resolve_profile(env)` (pure), `PUBLIC_LEAN_TOOL_NAMES`, `PUBLIC_READONLY_TOOL_NAMES`, and a pure
  `filter_tools(all_tools, profile)` helper.
- **Dependency direction is one-way:** this module must **not import `server.py`**. It exposes
  constants + pure helpers; `server.py` and the config generators consume it.
- It is **separate from** internal `agent/tool_groups.py`. The taxonomy *concept* may be reused; the
  internal *sets* are not (they serve RookChat/worker dispatch, a different layer — see §9).

---

## 7. Config generation and docs scope

**Lean is external-only.** Default new *external* (Codex/Cursor/Windsurf) configs to `lean`; leave
Claude Code / panel-source configs on `full`.

### 7.1 Two generation seams, both write Claude *and* Codex configs

- **`doctor.py`:** `_build_expected_env()` ([`doctor.py:51`](../../../mcp_server/src/rook/doctor.py))
  is **shared** — it feeds both the Claude MCP entry (`_build_expected_mcp_entry`,
  [`doctor.py:73`](../../../mcp_server/src/rook/doctor.py)) and the Codex TOML
  (`_generate_codex_toml`, [`doctor.py:82`](../../../mcp_server/src/rook/doctor.py)).
- **`install.ps1`:** a separate generator writing Claude `.mcp.json`
  ([`install.ps1:1005`](../../../install.ps1)), `.claude.json`
  ([`install.ps1:1037`](../../../install.ps1)), and Codex TOML
  ([`install.ps1:1132`](../../../install.ps1)+, already threading a `RookMode` param).

### 7.2 Hard requirement (the shared-env trap)

`ROOK_MCP_TOOL_PROFILE=lean` is injected **only in the Codex/external writer** in each system
(`_generate_codex_toml` / `_write_codex_config`; the `install.ps1` Codex path). It **must not** be
added to a **shared** env helper such as `doctor._build_expected_env()` — that helper feeds both Claude
and Codex, so an unconditional edit would make the **panel lean**, violating §2 invariant 4.
`ClaudePanelMcpConfigBuilder` deep-clones the existing `rook` env, so any `lean` that reaches a Claude
config is inherited by the panel.

### 7.3 Config rules

- **Claude Code / panel-source configs:** omit `ROOK_MCP_TOOL_PROFILE` ⇒ `full`.
- **Codex/Cursor/Windsurf configs & docs:** explicitly set `ROOK_MCP_TOOL_PROFILE=lean`.
- **Existing configs:** unchanged unless the user explicitly runs a migration/fix action.
- A profile a user *manually* places in a Claude config is honored (and inherited by the panel) — that
  is user intent, not default rollout.

### 7.4 Stale-doc correction (part of this campaign)

Active docs had stale pre-campaign tool-count language; the live `list_tools()` surface is **427** (430 static `Tool(...)` defs
minus the 3 deprecated-interactive tools gated out by default, §1). Correct the count across
`CLAUDE.md`, `AGENTS.md`, `docs/`, and memory so future reviewers do not argue from stale numbers. The
§8 snapshot test becomes the authoritative count going forward.

---

## 8. Testing contract (non-negotiable)

1. **Pure resolver:** `resolve_profile(env)` unit tests — absent ⇒ full; `full`/`lean`/`readonly` map
   through; invalid ⇒ raises (startup-failure path asserted separately).
2. **Profile snapshots (counts + names):** pin the exact tool name set for `absent`, `full`, `lean`,
   `readonly`, taken against **live `list_tools()`** output (not the static `Tool(...)` defs).
   - `full` set **==** live `list_tools()` — **427** in the default (interactive-learning-disabled)
     config; 430 if `_interactive_command_learning_enabled()` is set. Pin the default (427); assert the
     flag state so the snapshot is deterministic.
   - `absent` set **==** `full` set.
   - `lean` set **==** the pinned 17 (§4).
   - `readonly` set **==** `PUBLIC_READONLY_TOOL_NAMES` (145), a strict subset of `full`.
   - **Maintenance contract (called out, not free):** adding a new MCP tool now *requires* updating the
     `full` snapshot, and a deliberate decision whether it joins `lean`/`readonly`. The snapshot is the
     drift gate.
3. **Sentinel exclusion:** assert every name in §5.4 is absent from `readonly`.
4. **Stale-client rejection (`call_tool` wall):** with `readonly` active, calling a mutator returns the
   `tool_profile_blocked` envelope. Representative cases **must include `rhino_layer_visibility` and
   `rhino_select`** (the "not geometry-creation ⇒ readonly" fallacy), plus `gh_edit` and
   `rhino_transform`/`rhino_create`.
5. **No side effects on denial:** a blocked `readonly` call is **not** recorded as a tool observation
   and injects no knowledge; it does not invoke `targeting.policy_for_tool`.
6. **`lean` is list-only:** with `lean` active, a mutator hidden from `list_tools()` (e.g. `gh_edit` is
   *in* lean, but pick a non-lean mutator like `rhino_create`) is **still callable** via `call_tool()`
   — assert no profile rejection in `lean`.
7. **Config generation (both seams, separately):** `doctor`-generated and `install.ps1`-generated
   Codex configs contain `ROOK_MCP_TOOL_PROFILE=lean`; the corresponding Claude configs do **not**.
   Assert `_build_expected_env()` output contains no profile key (the shared-env guard).
8. **Committed partition check (replaces the throwaway audit script):** a committed test asserts the
   structural invariants the local audit verified — `PUBLIC_READONLY_TOOL_NAMES` is disjoint from the
   sentinel set (§5.4), is a strict subset of live `full`, and that `readonly ∪ excluded` partitions the
   full live surface with no gaps or overlaps. The per-tool read/write *judgment* stays the documented
   human audit (§5.5); this test pins its structural consequences so drift is caught when tools change.

---

## 9. Out of scope (YAGNI — explicitly deferred)

- Domain slices (`grasshopper`/`rhino`/`bim`/`vision`/`director`).
- Public meta-tools (`request_tools`/`search_tools` as MCP tools) and any `tools.listChanged`-driven
  dynamic expansion.
- A generic dynamic router (`rook_call_tool`).
- Depending on client `defer_loading` / `tool_search`.
- `lean` for the Claude Code panel.
- **Any change to the LM5D worker surface.** The worker action surface is bounded at a *different layer*
  — RookChat's internal `ToolRegistry` over HTTP, not public MCP `list_tools()`. This campaign and
  LM5D share only the *taxonomy concept*; they do not share code paths. Keeping them separate is a
  requirement, not an accident.

---

## 10. Rollout posture

Build the boring, auditable thing first: static env-driven profiles, `full` preserved as the
absent-default compatibility path, `readonly` enforced server-side, snapshot + rejection tests, and
docs pointing external clients at `lean`. Defer dynamic search/describe/execute until there is
telemetry from real Rook workflows that justifies the additional surface and safety burden.
