# Rook Release Surface Hardening Roadmap

- **Status:** Active audit roadmap
- **Created:** 2026-07-31
- **Audit baseline:** `90242fa4f09abf8f3b8ec994044787b61e77b446` (`origin/main`)
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
3. **Do not preserve dead product code as backup.** Git history is the backup. A
   retired release surface should be removed from source, build, installer, registry,
   tests, and documentation together.
4. **Preserve historical evidence.** Existing specifications, plans, reports, and
   postmortems remain unchanged unless they contain an active security/privacy issue or
   a broken provenance link. Current guidance belongs in active documents.
5. **Treat distributed contracts atomically.** A tool, skill, or UI capability is not
   shipped unless its runtime, schema, documentation, packaging, upgrade behavior, and
   validation agree.
6. **Do not destabilize verified runtime work.** Release hardening must not refactor the
   accepted Grasshopper/Rhino.Inside.Revit lifecycle or RookBIM identity corrections
   merely to make release cleanup convenient.
7. **Require fresh evidence before release.** Source-shape tests are useful guards but
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

**Recommended disposition:** Unless product ownership explicitly admits and tests these
dependencies, remove RoadCreator/RookRoads skills and `rc_*` discovery, and remove Wasp
instructions from general-purpose skills. Review native `road_*` tools separately;
their native fallback means they are not automatically part of the external-plugin
removal.

### Confirmed evidence

- `design-road` and `masterplan-roads` require separate RookRoads/RoadCreator plugins.
- Full MCP discovery includes approximately 40 `rc_*` tools and two `road_*` tools.
- `rc_*` target selection is special-cased to a `roadcreator` plugin type.
- General Grasshopper skills contain Wasp-specific reference material.
- Build and developer scripts also assume sibling RookRoads and SA_Banana repositories
  in places.

### Required product decisions

For each of RoadCreator/RookRoads, Wasp, and SA_Banana, choose exactly one state:

1. **Supported:** define versions, installation, discovery, degradation behavior,
   ownership, automated coverage, and a live acceptance host.
2. **Optional experimental:** exclude from the default installer/profile/docs and admit
   it through a separately versioned extension contract.
3. **Unsupported:** remove default schemas, dispatch, targeting, skills, docs, examples,
   build assumptions, public marketing, and upgrade residue.

### Exit criteria

- Every external dependency has an explicit support state and owner.
- Unsupported dependencies are absent from default tool discovery and installed skills.
- Retained native road tools are documented according to their actual native behavior,
  without implying RoadCreator availability.
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

### Exit criteria

- Every confirmed baseline mismatch has at least one automated guard where automation is
  meaningful.
- Guard fixtures demonstrate that the checks fail on the former bad state.
- Live-host gates remain explicit for behavior that source checks cannot prove.
- The build/release skill invokes the audit before packaging and again against staged
  installer/public-promotion payloads.

## Sequencing and dependency map

### Wave A — Product decisions and containment

1. Decide external-plugin support states (RS-05).
2. Approve RUI retirement while preserving panel evaluation (RS-01/RS-02).
3. Approve the Codex lean-plus-gateway direction (RS-03).
4. Freeze new public capability claims until promotion controls exist (RS-07).

### Wave B — Remove contradictions at their source

1. Retire the RUI and obsolete installer/registry residue (RS-01).
2. Remove or isolate unsupported integrations (RS-05).
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

## Immediate next action

Review and approve the three Wave A product decisions: external-plugin support, RUI
retirement, and Codex lean-plus-gateway skills. After those decisions are recorded,
write separate focused specifications for RS-01/RS-02, RS-03–RS-05, and RS-09/RS-11.
Documentation and public-promotion workstreams may then reference those approved
contracts instead of guessing future product behavior.
