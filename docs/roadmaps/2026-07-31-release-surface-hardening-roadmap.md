# Rook Release Surface Hardening Roadmap

- **Status:** Active audit roadmap
- **Created:** 2026-07-31
- **Audit baseline:** `90242fa4f09abf8f3b8ec994044787b61e77b446` (`origin/main`)
- **Last reconciled:** 2026-08-01 at `f22904c21474b616e2fe3487f686c5632bba8a37`
- **Scope:** Installer, release metadata, installed documentation, public documentation,
  agent skills, optional integrations, managed UI/RUI packaging, upgrade behavior, and
  release validation
- **Out of scope:** Reopening the accepted Grasshopper lifecycle or RookBIM identity
  designs without new runtime evidence

## Purpose

Rook's core runtime has advanced faster than its release shell. The current source
contains verified Grasshopper and RookBIM corrections, but the installer and public
distribution still carry stale prerequisites, conflicting contracts, broken UI
registration, unsupported-plugin assumptions, copied skill drift, and incomplete
release gates.

This document is the durable program ledger for correcting that release surface. It
records what is already proven, what still requires investigation or product judgment,
and the evidence required before an item may be closed. It is not an implementation
plan. Any workstream that changes runtime behavior or a public contract must receive a
focused specification and implementation plan before code changes begin.

## Governing principles

1. **Production behavior is authoritative.** Documentation, skills, schemas, and
   marketing must describe the behavior that the shipped runtime actually provides.
2. **Keep the solution small.** Prefer removal, generated validation, or one clear
   source of truth over compatibility layers and new frameworks.
3. **Contain unsupported surfaces before deleting internals.** Remove or deny
   user-facing and agent-facing discovery, invocation, guidance, and exact Rook-owned
   installed residue first. Dormant implementation may remain when deleting it would
   expand risk without improving the supported product. Full code removal requires an
   explicit workstream decision; cleanup is not a license for broad purges.
4. **Use Git history as the backup for fully retired artifacts.** When a workstream
   explicitly chooses full retirement, do not keep alternate live copies or speculative
   compatibility paths merely as backup.
5. **Preserve historical evidence.** Existing specifications, plans, reports, and
   postmortems remain unchanged unless they contain an active security/privacy issue or
   a broken provenance link. Current guidance belongs in active documents.
6. **Treat distributed contracts atomically.** A tool, skill, or UI capability is not
   shipped unless its runtime, schema, documentation, packaging, upgrade behavior, and
   validation agree.
7. **Do not destabilize verified runtime work.** Release hardening must not refactor the
   accepted Grasshopper/Rhino.Inside.Revit lifecycle or RookBIM identity corrections
   merely to make release cleanup convenient.
8. **Require fresh evidence before release.** Source-shape tests are useful guards but
   do not replace clean-install, upgrade, standalone Rhino, Grasshopper, RiR, RookBIM,
   Claude, and Codex acceptance where those surfaces are supported.

## Status vocabulary

| Status | Meaning |
|---|---|
| `confirmed` | The audit established the mismatch from current source or distribution evidence. |
| `decision_required` | Product ownership must choose the supported surface before implementation. |
| `ready_for_spec` | The direction is bounded enough for a focused design/specification. |
| `investigating` | More source, installer, or live-host evidence is required. |
| `planned` | An approved implementation plan exists. |
| `in_progress` | Implementation is underway on an isolated branch/worktree. |
| `verified` | The change passed its documented automated and live acceptance gates. |
| `deferred` | The item is explicitly excluded from the target release with rationale. |
| `removed` | The capability and its release residue were removed and upgrade cleanup was verified. |

Status changes must include a dated evidence link or commit. Do not mark an item
`verified` solely because its source diff looks correct.

## Program completion criteria

The release-surface program is complete when all of the following are true:

- Every shipped skill can execute through the MCP profile installed for its client.
- Unsupported external-plugin integrations are either removed completely or admitted
  through an explicit optional-integration contract and acceptance matrix.
- The legacy RUI is either fully functional and tested or absent from build output,
  runtime loading, installer payload, registry state, tests, and documentation.
- Shipped and public documentation states the correct prerequisites, architecture,
  tool behavior, supported hosts, and restart/reconnect requirements.
- All version-bearing release objects agree with the release version.
- The private source release and public `rook-release` promotion are one reviewable,
  hash-verifiable sequence.
- Clean install, upgrade, repair, rollback, uninstall, and removed-content cleanup are
  tested from representative prior releases.
- Supported UI panels and client connections pass live acceptance.
- Release guards fail on the classes of drift identified in this audit.

## Baseline audit summary

| ID | Priority | Initial status | Confirmed baseline finding |
|---|---:|---|---|
| RS-01 | P0 | `ready_for_spec` | Four of seven legacy RUI toolbar entries are missing, retired, or undefined. |
| RS-02 | P1 | `investigating` | Eto panels are independent of the RUI and have open live-behavior issues. |
| RS-03 | P0 | `ready_for_spec` | Codex is installed with the 20-tool `lean` profile while 10 of 11 copied skills directly name unavailable tools. |
| RS-04 | P1 | `confirmed` | Three manually maintained skill payloads have already drifted. |
| RS-05 | P0 | `decision_required` | RoadCreator/RookRoads and Wasp assumptions are embedded in shipped skills, docs, and MCP discovery. |
| RS-06 | P0 | `ready_for_spec` | Installed and pre-install docs state false prerequisites and stale behavior. |
| RS-07 | P0 | `ready_for_spec` | Public plugin metadata, skills, and website claims do not match the private release source. |
| RS-08 | P1 | `confirmed` | Version, repository URL, product-description, and wheelhouse defaults disagree. |
| RS-09 | P1 | `investigating` | Upgrades merge user skill directories and can retain removed Rook-owned content; client restart/reconnect and config-preservation gaps remain. |
| RS-10 | P1 | `ready_for_spec` | `gh_edit` is still advertised as atomic despite its accepted partial-success and verification contract. |
| RS-11 | P0 | `ready_for_spec` | Existing release guards pass while all preceding mismatches remain present. |

## Current progress snapshot

| Workstream | Current status | Reconciled evidence and remaining boundary |
|---|---|---|
| RS-01 | `ready_for_spec` | RUI suppression remains the next focused cleanup target. No RUI production or installer change has started. |
| RS-05 | RoadCreator/RookRoads `verified`; Wasp `investigating` | PR [#521](https://github.com/bringfire/Rook/pull/521) completed private user/agent surface containment, exact upgrade cleanup, focused tests, packaging, and installed smoke. Public promotion remains RS-07; Wasp admission remains separate. |
| RS-08 | `confirmed` with partial remediation | PR [#521](https://github.com/bringfire/Rook/pull/521) pinned the supported MCP 1.x dependency and aligned lock/wheelhouse verification. The broader version, URL, description, and runtime-anchor audit remains open. |
| RS-09 | `investigating` with partial remediation | PR [#521](https://github.com/bringfire/Rook/pull/521) proved exact, unconditional, link-safe cleanup for the two retired Codex skill directories while preserving siblings. General skill ownership, configuration preservation, reconnect, rollback, and uninstall behavior remain open. |
| RS-11 | `ready_for_spec` with expanded evidence | PRs [#524](https://github.com/bringfire/Rook/pull/524) and [#526](https://github.com/bringfire/Rook/pull/526) corrected two schema/dispatch/managed-selector mismatches. A focused selector-parity release guard is still required. |

## Workstream RS-01 — Retire the legacy RUI toolbar

**Recommended disposition:** Suppress and remove the RUI toolbar for the next release.
Retain the independently registered Eto panels and supported Rhino commands.

### Confirmed evidence

- [`src/Rook/UI/Rook.rui`](../../src/Rook/UI/Rook.rui) invokes
  `_ShowRookPanel`, `_StartRook`, and `_StopRook`, which are not current commands.
- The Bridge Status item does not have an executable current macro.
- Start/Stop Bridge conflicts with the architecture in which `RookNative` is the sole
  HTTP server and owns its lifecycle.
- `AIGumball` has both native and legacy managed implementations, making toolbar
  ownership ambiguous.
- [`src/Rook/Rook.csproj`](../../src/Rook/Rook.csproj) copies the RUI into every managed
  target output.
- [`src/Rook/RookPlugin.cs`](../../src/Rook/RookPlugin.cs) loads it programmatically in
  standalone Rhino.
- [`installer/RookSetup.iss`](../../installer/RookSetup.iss) installs three copies and
  registers the net8 copy as `RuiFile`.
- Current release guards require the RUI's presence but do not validate its macros
  against the installed command inventory.

### Investigation and implementation boundaries

- Inventory every RUI macro against native and managed command names before removal so
  no still-supported command is accidentally lost.
- Confirm that no panel requires RUI initialization as an undocumented side effect.
- Remove RUI source/payload references, programmatic loading, registry values,
  validation requirements, build/release checklists, and user documentation in one
  change set.
- Add upgrade cleanup for previously installed `Rook.rui` files and the `RuiFile`
  registry value.
- Do not replace the toolbar with a new UI in this workstream.

### Exit criteria

- No tracked production, installer, or active-documentation reference requires
  `Rook.rui`.
- Upgrade from the latest public installer removes Rook-owned toolbar residue without
  touching user-created Rhino toolbars.
- Standalone Rhino and RiR start without toolbar load warnings.
- Supported panel commands remain available and pass RS-02 acceptance.

## Workstream RS-02 — Verify and bound the surviving managed panels

**Recommended disposition:** Keep Rook Chat, Rook Vision, and Knowledge Graph only if
their current command and lifecycle behavior passes focused live acceptance.

### Confirmed evidence

- The three Eto panels are registered independently in
  [`src/Rook/RookPlugin.cs`](../../src/Rook/RookPlugin.cs).
- The RUI can therefore be retired without automatically removing the panels.
- GitHub issue [#188](https://github.com/bringfire/Rook/issues/188) records a
  `_ShowRookChat` false-negative through the generic command route even when the panel
  opens.
- GitHub issue [#154](https://github.com/bringfire/Rook/issues/154) records a
  Rook Vision gallery freeze while closing a playing video.

### Investigation checklist

- Test each panel from Rhino commands, supported MCP command dispatch, close/reopen,
  document switching, Rhino shutdown, and RiR where applicable.
- Distinguish transport false-negatives from panel-rendering defects.
- Verify WebView creation, disposal, and process cleanup.
- Decide whether each panel is a supported release capability, an experimental feature,
  or a removal candidate. Record that classification in active architecture docs.

### Exit criteria

- Every retained panel has a named command, an owner, a support classification, and a
  repeatable live acceptance case.
- Known false-success/false-failure behavior is corrected or documented as an explicit
  limitation with an issue and release note.
- Removed panels leave no command, registry, manifest, installer, or documentation
  residue.

## Workstream RS-03 — Make installed Codex skills compatible with the Codex profile

**Recommended disposition:** Retain the `lean` profile and make Codex skills use the
existing progressive-discovery gateway (`rook_tools_search`, `rook_tools_read`, and
`rook_tools_call`). Do not enable all 422 tools merely to accommodate copied skills.

### Confirmed evidence

- [`installer/post_install.py`](../../installer/post_install.py) sets
  `ROOK_MCP_TOOL_PROFILE=lean` for Codex.
- The lean profile advertises 20 tools.
- Ten of the eleven copied Codex skills directly name tools outside that profile.
- The remaining `project-setup` skill is Claude-specific: it creates `CLAUDE.md`,
  inspects `.claude`, references Claude configuration, and asks users to run Claude
  commands.
- Installed `AGENTS.md` already defines progressive discovery, but copied skill
  procedures and examples bypass it.

### Investigation checklist

- Build a generated skill-to-tool inventory from every shipped Codex `SKILL.md` and
  directly linked reference file.
- Determine which direct tool names are instructional examples and which are required
  executable calls.
- Convert retained Codex skills to the gateway contract or remove them from the Codex
  payload.
- Rewrite `project-setup` for Codex or stop shipping it to Codex; do not retain a
  Claude-branded compatibility copy.
- Validate that the gateway exposes enough schema and response detail for every retained
  workflow.

### Exit criteria

- A release test proves that every tool used by every shipped Codex skill is either in
  the installed profile or invoked through the gateway.
- No Codex skill instructs users to edit Claude-specific files or run Claude commands.
- The Codex onboarding document reports the actual profile behavior instead of claiming
  that nearly 400 tools are directly advertised.
- Representative retained skills complete live Codex smoke tests.

## Workstream RS-04 — Establish one authoritative skill source

**Recommended disposition:** Treat `.agents/skills` as the maintained source and derive
or validate the curated Claude and Codex payloads. Allow small platform-specific files
where client behavior genuinely differs; do not introduce a general templating system.

### Confirmed evidence

- Skills are currently copied among `.agents/skills`, `.claude/skills`, and the
  installer staging tree.
- The audit found real content differences in `chirp-cascade`, `design-grasshopper`,
  and `masterplan-roads`, in addition to expected developer-only omissions.
- Public `rook-release` skills have diverged further from the private source.

### Investigation checklist

- Classify skills as developer-only, Claude, Codex, shared end-user, or unsupported.
- Record the curated payload in one machine-readable allowlist.
- Decide whether client-specific variants live beside the source skill or are generated
  through a small deterministic transform.
- Add validation for linked references, client branding, tool/profile compatibility,
  and unexpected payload drift.

### Exit criteria

- One command deterministically produces or verifies the installer skill payload.
- Public and private copies are byte-identical where they claim to be shared.
- Adding, removing, or renaming a skill requires one authoritative edit plus an explicit
  payload decision.

## Workstream RS-05 — Decide the supported external-plugin surface

**Current status:** `verified` for private RoadCreator/RookRoads surface containment;
`investigating` for Wasp admission. Public promotion remains tracked by RS-07.

**Approved disposition:** RoadCreator and RookRoads are unsupported and must be contained
at Rook's user-facing and agent-facing boundaries. Their dormant adapter, bridge,
targeting, native, historical, and compatibility implementation may remain when it is
not visible or invocable through those boundaries. Wasp remains a powerful optional
Grasshopper integration pending a focused admission audit. Native `road_*` tools and
Wasp are outside the RoadCreator/RookRoads containment change.

### Confirmed evidence

- `design-road` and `masterplan-roads` require separate RookRoads/RoadCreator plugins.
- Full MCP discovery includes exactly 40 `rc_*` tools and two `road_*` tools at the audit
  baseline.
- `rc_*` target selection is special-cased to a `roadcreator` plugin type.
- General Grasshopper skills contain Wasp-specific reference material.
- Build and developer scripts also assume sibling RookRoads and SA_Banana repositories
  in places.

### Approved support split

| Integration | Status | Release contract |
|---|---|---|
| RoadCreator/RookRoads | Unsupported and contained | Remove their shipped skills and active user/agent guidance. Omit `rc_*` tools from MCP discovery, profiles, progressive search/read, and agent catalogs; deny direct MCP and internal-agent dispatch through the existing lifecycle-containment mechanism. Leave non-exposed implementation in place. |
| Wasp | Optional experimental pending admission | Preserve its current material. Do not assume installation or claim default support. Audit versions, capability detection, absence behavior, guidance, and a representative live workflow before promotion. |
| SA_Banana | Decision not included | Make no support or containment change under this workstream. Track independently if needed. |

The RoadCreator/RookRoads containment boundary is specified in
[`2026-07-31-roadcreator-rookroads-surface-containment-design.md`](../superpowers/specs/2026-07-31-roadcreator-rookroads-surface-containment-design.md).
It was implemented and accepted in PR [#521](https://github.com/bringfire/Rook/pull/521),
merged as `3ba27ebe97a3295a5296dd0e1809073863367376`. Wasp admission requires a
separate evidence-driven specification; it is not part of the containment
implementation.

### Exit criteria

- Every externally visible dependency has an explicit support state.
- RoadCreator/RookRoads are absent from tool discovery, progressive disclosure, agent
  catalogs, installed skills, active user guidance, and public claims.
- Direct attempts to invoke `rc_*` tools are denied before arguments or downstream
  handlers are touched.
- Retained native road tools are documented according to their actual native behavior,
  without implying RoadCreator availability.
- Wasp content is not removed by the RoadCreator/RookRoads containment change.
- Clean machines without external plugins receive no broken skill or advertised tool
  path.

## Workstream RS-06 — Correct the active documentation surface

**Recommended disposition:** Update shipped, installed, contributor-entry, and public
documents only. Preserve historical specifications and reports as evidence.

### Confirmed evidence

- The repository contains 901 tracked Markdown files; 605 are under the historical
  `docs/superpowers` specification/plan/report tree.
- [`README.md`](../../README.md), [`QUICK_START.md`](../../QUICK_START.md),
  [`AGENT_SETUP.md`](../../AGENT_SETUP.md), and
  [`installer/pre-install-readme.txt`](../../installer/pre-install-readme.txt) claim that
  the Windows installer requires system Python 3.10+. It currently ships sealed CPython
  3.11.9.
- [`mcp_server/README.md`](../../mcp_server/README.md) describes a Claude-only,
  source-install, 113-tool, Anthropic-key workflow rather than the current product.
- `QUICK_START.md` contains an installed-layout-relative link that resolves to the wrong
  location.
- [`docs/CURRENT_ARCHITECTURE.md`](../CURRENT_ARCHITECTURE.md) has an incomplete managed
  command inventory.
- [`docs/AGENT_ARCHITECTURE.md`](../AGENT_ARCHITECTURE.md) contains high-drift internal
  implementation counts and is unnecessarily included in the installed documentation
  payload.

### Document classes

| Class | Examples | Maintenance rule |
|---|---|---|
| Shipped user guidance | Quick start, agent setup, troubleshooting, pre-install text | Must pass current installer/runtime contract checks. |
| Active architecture | `CURRENT_ARCHITECTURE.md`, installer ownership instructions | Must match live route and process ownership. |
| Contributor/release guidance | root instructions, build/release skill, MCP README | Must match supported development and release workflows. |
| Public product guidance | `rook-release` README/site/plugin package | Must match the exact promoted release. |
| Historical evidence | specs, plans, reports, postmortems | Preserve; supersede through links rather than rewriting history. |

### Exit criteria

- No shipped document requires system Python for the sealed Windows installer.
- Counts and availability claims distinguish full, lean, client, and optional profiles;
  mutable exact counts are generated or avoided in marketing copy.
- Installed relative links are validated against their installed destination layout.
- Active docs describe native server ownership, managed companion responsibilities,
  Grasshopper partial-success behavior, and RookBIM prerequisites accurately.
- Internal high-drift documentation is not installed as user guidance.

## Workstream RS-07 — Make public release promotion a first-class release stage

**Recommended disposition:** Add a reviewed promotion PR from private release source to
[`bringfire/rook-release`](https://github.com/bringfire/rook-release). Do not rely on
manual copying or direct pushes.

### Confirmed evidence

- The latest public installer release is newer than the public plugin manifest version.
- Public `.claude-plugin` manifests remain at `1.5.9` while the audited private runtime
  is `1.5.16`.
- Twenty-one of thirty-seven public skill files differ from current private skill files.
- Public pages advertise Director and multi-agent capabilities as shipping even though
  the active architecture explicitly retires or contains those paths.
- The private build/release workflow creates a private GitHub release but contains no
  mandatory public-repository synchronization or promotion gate.

### Investigation checklist

- Define the exact public artifact allowlist: installer, checksums/manifests, plugin
  package, skills/hooks, public README/site changes, release notes, and provenance.
- Generate a promotion manifest with source commit, release version, file paths, lengths,
  and hashes.
- Create a public PR and require public-content checks before creating or updating the
  release.
- Remove retired Director/multi-agent claims and unsupported-plugin claims from public
  navigation as well as leaf pages.

### Exit criteria

- A public release can be traced to one reviewed private source commit and one reviewed
  public promotion commit.
- Public plugin versions, skills, hooks, site claims, installer, and release notes agree.
- Promotion fails on unreviewed file drift, missing artifacts, or hash disagreement.

## Workstream RS-08 — Normalize version and product metadata

**Recommended disposition:** Extend the existing release version audit rather than
introducing a new version service. Remove default version literals from build helpers
where the release command can provide or derive the version.

### Confirmed evidence

- The release checklist updates seven runtime/installer files but omits
  `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
- [`scripts/python-runtime/build-rook-python-wheelhouse.ps1`](../../scripts/python-runtime/build-rook-python-wheelhouse.ps1)
  defaults to stale version `1.5.10`.
- Managed and native plugin metadata still reference the retired `bringfire/Rhino_AI`
  repository in source/local-deploy paths.
- Some descriptions still claim the managed companion owns an HTTP server or describe
  the native plugin as Claude-specific.
- Build/reference documentation disagrees about whether net7 or net8 is the registration
  anchor; the current installer uses net8.
- PR [#521](https://github.com/bringfire/Rook/pull/521) corrected one release-critical
  dependency boundary by pinning `mcp==1.28.1` and verifying that the wheelhouse and
  installed runtime cannot select MCP 2.x. The remaining metadata findings above are
  unchanged.

### Exit criteria

- A release audit enumerates and validates every version-bearing file.
- Repository, update, and support URLs point to the intended public destinations.
- Plugin descriptions are client-neutral and match actual process ownership.
- Release helpers require or derive the version; they do not carry stale operational
  defaults.
- Local deployment and public installer registration write equivalent supported
  metadata.

## Workstream RS-09 — Harden upgrade, repair, configuration, and reconnect behavior

**Recommended disposition:** Preserve user configuration fail-closed, remove only
explicitly Rook-owned obsolete content, and make client restart/reconnect requirements
observable and consistent.

### Confirmed evidence

- Installer staging deletes its private skill staging directory, but
  [`installer/post_install.py`](../../installer/post_install.py) merges children into
  `~/.codex/skills` using `dirs_exist_ok=True`; removed files and directories can survive
  an upgrade.
- PR [#521](https://github.com/bringfire/Rook/pull/521) added exact-path migration cleanup
  for the retired `design-road` and `masterplan-roads` Codex skill directories on every
  install and repair. It is link-safe, idempotent, preserves sibling skills, and does not
  generalize deletion beyond those two Rook-owned targets.
- GitHub issues [#187](https://github.com/bringfire/Rook/issues/187) and
  [#243](https://github.com/bringfire/Rook/issues/243) record stale/reconnect behavior
  after installation or process restart.
- GitHub issue [#239](https://github.com/bringfire/Rook/issues/239) records configuration
  replacement/data-loss concerns. Some code paths have since improved, but every client
  configuration path still requires explicit preservation testing.

### Investigation checklist

- Define ownership markers or an exact allowlist for Rook-installed skill directories;
  never broadly delete a user's skill root.
- Test upgrade from representative public versions with removed and modified Rook-owned
  skills plus unrelated user skills.
- Exercise valid, malformed, and partially writable Claude/Codex configuration files.
- Test running-client install/repair behavior and document when restart is unavoidable.
- Verify rollback and uninstall leave user-owned configuration and skills intact.

### Exit criteria

- Removed Rook-owned skills and references do not survive an upgrade.
- Unrelated user skills and configuration are byte-preserved.
- Malformed configuration fails closed or produces a recoverable backup without silently
  replacing unrelated content.
- Supported clients reconnect automatically or receive one accurate, consistent restart
  instruction backed by live acceptance.

## Workstream RS-10 — Correct the Grasshopper mutation contract everywhere

**Recommended disposition:** Describe `gh_edit` as one batched request with
operation-level outcomes, partial-success evidence, scheduling state, and required
verification. Reserve the word “atomic” for operations that actually provide rollback
semantics.

### Confirmed evidence

- [`AGENT_SETUP.md`](../../AGENT_SETUP.md), MCP schemas in
  [`mcp_server/src/rook/server.py`](../../mcp_server/src/rook/server.py), agent prompts,
  and managed comments still describe `gh_edit` as atomic.
- Current safe skills inspect `partial_success`, `verified`, operation errors,
  `solve_scheduled`, and follow-up state. That accepted behavior is not an all-or-nothing
  transaction.

### Exit criteria

- The managed response, Python schema, prompts, Claude skills, Codex skills, installed
  docs, public docs, and examples use one normative contract.
- No instruction recommends retrying an entire partially successful batch.
- Contract tests reject reintroduction of global atomicity claims while allowing accurate
  operation-specific atomic claims elsewhere.
- Standalone and RiR examples demonstrate bounded verification and missing-work-only
  recovery.

## Workstream RS-11 — Expand release guards to cover the release users receive

**Recommended disposition:** Add one small release-surface audit entry point that calls
focused checks. Avoid building a general policy framework.

### Confirmed evidence

The current installer guard suite passes even though it does not detect:

- false Python prerequisites;
- Codex skill/profile incompatibility;
- stale public plugin versions and skills;
- broken installed-layout links;
- invalid RUI command macros;
- unsupported-plugin claims;
- stale repository URLs and descriptions;
- `gh_edit` contract contradictions; or
- missing cleanup for removed user-profile skills.

Subsequent focused fixes exposed another release-guard gap:

- PR [#524](https://github.com/bringfire/Rook/pull/524) proved that indexed
  `gh_connect` selectors were accepted at the MCP boundary but ignored by the managed
  handler, causing a silent mutation of input 0.
- PR [#526](https://github.com/bringfire/Rook/pull/526) proved that `outputIndex` on
  `gh_inspect_output` was ignored and silently degraded to output 0.
- Both fixes now preserve selector presence, reject conflicts and invalid explicit
  values, and return resolved parameter metadata. The release audit still lacks a
  reusable focused guard against reintroducing this boundary mismatch.

### Required guard categories

1. Version and metadata agreement.
2. Installer source/output inventory agreement.
3. Installed-layout Markdown link validation.
4. Skill allowlist, linked-reference, branding, and profile compatibility.
5. Command/RUI macro agreement while the RUI exists; absence checks after retirement.
6. Unsupported-integration reference scans scoped to active production and shipped docs.
7. Public-promotion manifest and hash agreement.
8. Upgrade fixtures for removed Rook-owned content and preserved user content.
9. Normative contract vocabulary checks for high-risk distributed contracts.
10. Grasshopper selector parity across MCP schema, Python dispatch, and managed
    resolution, including proof that an explicit invalid selector cannot degrade to
    omission or a default port.

### Exit criteria

- Every confirmed baseline mismatch has at least one automated guard where automation is
  meaningful.
- Guard fixtures demonstrate that the checks fail on the former bad state.
- Live-host gates remain explicit for behavior that source checks cannot prove.
- The build/release skill invokes the audit before packaging and again against staged
  installer/public-promotion payloads.

## Sequencing and dependency map

### Wave A — Product decisions and containment

1. RoadCreator/RookRoads private containment is complete. Keep the Wasp admission audit
   separate and evidence-driven (RS-05).
2. Specify RUI retirement while preserving independent panel evaluation (RS-01/RS-02).
3. Approve the Codex lean-plus-gateway direction (RS-03).
4. Freeze new public capability claims until promotion controls exist (RS-07).

### Wave B — Remove contradictions at their source

1. Retire the RUI and obsolete installer/registry residue (RS-01).
2. Promote the completed RoadCreator/RookRoads containment through the public release
   stage without reopening dormant internals (RS-05/RS-07).
3. Establish the skill source/allowlist and correct Codex skills (RS-03/RS-04).
4. Correct the Grasshopper contract vocabulary (RS-10).

### Wave C — Rebuild the active release surface

1. Update active private and installed documentation (RS-06).
2. Normalize versions, URLs, descriptions, and runtime anchors (RS-08).
3. Harden upgrade/config/reconnect behavior (RS-09).
4. Add release-surface guards (RS-11).

### Wave D — Promote and accept the complete installer

1. Build the full suite and installer from a clean immutable commit.
2. Run clean-install, upgrade, repair, rollback, and uninstall matrices.
3. Run supported standalone Rhino, panels, Grasshopper, RiR, RookBIM, Claude, and Codex
   smoke matrices.
4. Create and review the public promotion PR (RS-07).
5. Verify public artifacts and release metadata against the promotion manifest.

Do not combine all waves into one pull request. Each PR must leave the product in a
coherent state and state which release gate remains closed.

## Release acceptance matrix

| Layer | Required evidence |
|---|---|
| Source | Clean immutable commit, expected file scope, diff/whitespace/link checks, complete version audit. |
| Build | Native, managed companion, RookBIM, Python wheelhouse, and installer build from documented toolchains. |
| Inventory | Staged and installed path/length/hash/count manifests with no stale files. |
| Clean install | No system-Python dependency; correct Rhino registration; no retired RUI or unsupported skill residue. |
| Upgrade | Representative prior public version; removed Rook content cleaned; user content preserved. |
| Repair | Idempotent configuration and inventory; accurate locked-process behavior. |
| Uninstall/rollback | Rook-owned artifacts removed/restored without deleting user-owned configuration or skills. |
| Standalone Rhino | Plugin load, supported commands, panel lifecycle, Grasshopper create/edit/solve/verify. |
| RiR/Revit | Supported Rhino.Inside/Revit load, Grasshopper lifecycle, RookBIM active-document/query/identity/export smoke. |
| Claude | Marketplace/plugin install, progressive discovery, representative retained skills. |
| Codex | Lean profile, gateway-driven retained skills, reconnect/restart behavior. |
| Public promotion | Reviewed public PR, version/content agreement, signed or hashed artifacts, accurate site/release notes. |

## Change log and evidence ledger

Append one row for every roadmap status change. Link the specification, plan, PR, commit,
test report, or decision record that supports it.

| Date | Workstream | From | To | Evidence | Notes |
|---|---|---|---|---|---|
| 2026-07-31 | RS-01–RS-11 | — | Baseline statuses | Audit of `90242fa4f09abf8f3b8ec994044787b61e77b446` | Initial release-surface audit; no product files changed. |
| 2026-07-31 | RS-05 | `decision_required` | `ready_for_spec` / `investigating` | [Road surface-containment design](../superpowers/specs/2026-07-31-roadcreator-rookroads-surface-containment-design.md) | RoadCreator/RookRoads classified unsupported and contained only at user/agent boundaries; Wasp retained; SA_Banana unchanged. |
| 2026-08-01 | RS-05 | `ready_for_spec` | RoadCreator/RookRoads `verified`; Wasp `investigating` | PR [#521](https://github.com/bringfire/Rook/pull/521), merge `3ba27ebe` | Private containment, exact retired-skill migration, packaging, and installed smoke passed. Public promotion remains RS-07. |
| 2026-08-01 | RS-08 | `confirmed` | `confirmed` with partial remediation | PR [#521](https://github.com/bringfire/Rook/pull/521), merge `3ba27ebe` | Pinned MCP 1.28.1 and verified wheelhouse/installed-runtime compatibility; broader metadata normalization remains open. |
| 2026-08-01 | RS-09 | `investigating` | `investigating` with partial remediation | PR [#521](https://github.com/bringfire/Rook/pull/521), merge `3ba27ebe` | Exact link-safe cleanup for two retired Rook-owned Codex skills verified; general configuration and reconnect work remains open. |
| 2026-08-01 | RS-11 | `ready_for_spec` | `ready_for_spec` with expanded evidence | PRs [#524](https://github.com/bringfire/Rook/pull/524) and [#526](https://github.com/bringfire/Rook/pull/526), merges `fabf9576` and `f22904c2` | Added selector-parity as a required release-guard category after two silent-default defects were fixed and accepted. |

## Immediate next action

Write the focused RS-01 RUI-retirement specification. It must inventory every macro,
confirm that the independently registered panels do not depend on RUI initialization,
remove only the RUI source/build/installer/registry/active-guidance surface, and define
exact upgrade cleanup plus standalone/RiR acceptance. It must not create a replacement
toolbar or broaden into panel redesign.

After RS-01 review, proceed to RS-02 panel acceptance and then the RS-03/RS-04 Codex
skill-source work. Do not reopen the verified RoadCreator/RookRoads, Grasshopper
selector, lifecycle, or RookBIM corrections without new runtime evidence.
