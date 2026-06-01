# Rook Ecosystem Master Decomposition

Date: 2026-05-31

Status: Approved design. This is not an implementation plan.

Related context:

- `docs/superpowers/specs/2026-05-31-rook-ecosystem-architecture-roadmap.md`
- `docs/CURRENT_ARCHITECTURE.md`
- `docs/AGENT_ARCHITECTURE.md`
- `docs/TROUBLESHOOTING.md`
- `installer/RookSetup.iss`
- `installer/post_install.py`
- `scripts/deploy-local-testing.ps1`
- `scripts/validate-release-artifacts.ps1`

## Purpose

This document decomposes the Rook ecosystem architecture roadmap into execution
phases. It is the map between the roadmap and future implementation plans.

The purpose is sequencing, not code design. This document defines:

- what each phase is allowed to change;
- what each phase must not change;
- what new truth each phase introduces;
- how reviewers should reject phase-boundary violations;
- what validation gates must exist before later phases can proceed.

This spec authorizes only the Phase 1 implementation plan immediately. Phase 2
through Phase 5 implementation plans are gated on evidence learned from earlier
phases.

## Three Planes

The roadmap should be understood through three planes:

```text
Behavior plane: what actually runs today
State plane: what Rook says exists / is ready / blocked / missing
Install plane: what files, modules, runtimes, configs, and sidecars are present
```

Early work adds the state plane over the current behavior plane. Then it makes
the install plane explicit. Then it correlates state with install evidence.
Only after that may a domain propose structural changes to behavior, loading,
route ownership, or physical layout.

The safety rule is:

```text
Do not move things first.
Name them first.
Observe them second.
Report them third.
Only then consider changing load, path, or ownership.
```

## Global Invariants

These invariants apply to every PR derived from this roadmap:

- No behavior change unless the phase explicitly permits it.
- No route ownership change before domain readiness and diagnostics exist.
- No installer path move before module manifests and upgrade validation exist.
- No broad readiness bit may replace domain-specific state.
- Phase 1 reports current behavior and known dependencies; it does not change
  availability semantics.
- RookNative remains the sole public Rhino HTTP/discovery surface.
- The managed companion remains internal.
- Current deferred/eager companion loading remains the early compatibility
  baseline.
- A capability may be discoverable even when unavailable, degraded, missing
  dependencies, unlicensed, or not loaded.
- A Rook module is integrated only when install evidence, runtime capability
  state, diagnostics, and client-facing discovery all agree.
- Capability state must be derived from real probes, registrations, install
  evidence, or explicit unavailable providers. It must not become a
  hand-maintained second truth.

## Phase Template

Each phase plan should use this template:

```text
Phase goal
New truth introduced
Phase exit question
What changes
What explicitly does not change
Deliverables
Domain boundaries touched
Compatibility invariants
Validation gates
Rollback / escape hatch
What later phases must not assume yet
Candidate follow-up plans / PR slices
```

The phase exit question is required:

```text
What can Rook truthfully say after this phase that it could not say before?
```

That question prevents phases from becoming generic architecture cleanup.

## Phase 1: Runtime Capability Discovery

### Phase Goal

Add a runtime capability/discoverability contract over the current
architecture.

### New Truth Introduced

Runtime capability state exists. It reports current behavior and known
dependencies only. It does not change availability semantics.

### Phase Exit Question

What can Rook truthfully say after Phase 1 that it could not say before?

Expected answer:

> Rook can truthfully report which capability domains exist, whether they are
> ready, unavailable, degraded, blocked, loading, or not loaded, and what real
> evidence supports that state.

### What Changes

- Add a versioned capability schema.
- Add a native public capability surface. The default route is
  `GET /capabilities` unless the Phase 1 implementation plan identifies a
  stronger compatible route.
- Add compact capability summary to native discovery if appropriate.
- Add domain IDs and state records for initial domains:
  - `native.core`
  - `native.command_control`
  - `gh.bridge`
  - `gh.canvas`
  - `bim.rhino_inside_revit`
  - `chat.ui`
  - `vision.media`
  - `viewport.capture`
  - `block.definition_mutation`
  - `mcp.runtime`
  - `knowledge.stores`
  - `chirp.runtime`
  - `licensing.entitlement` as reserved/future
- Derive state from real probes, registrations, current runtime facts, already
  directly available install evidence, or explicit unavailable providers.
- Use install evidence only where it is already directly available. Do not
  introduce installer module manifests or full runtime/install correlation in
  Phase 1.

### Required Schema Concepts

Phase 1 credibility depends on separating existence from readiness and on
showing why a state can be asserted.

Required concepts:

```text
domain_id
declared
installed
state
state_source or evidence
reason_code
retryable
message
routes
operations
diagnostics
schema_version
```

Example:

```text
domain_id: bim.rhino_inside_revit
declared: true
installed: unknown
state: blocked_by_host
reason_code: not_rhino_inside
evidence: Rhino is not hosted inside Revit
state_source: managed rookbim unavailable provider
```

`declared` means the domain exists in Rook's product model. `ready` or `state`
describes whether it can be used in the current runtime. A future client must
be able to discover `bim.rhino_inside_revit` even when the current host cannot
use it.

### What Explicitly Does Not Change

- No route ownership changes.
- No companion loading changes.
- No installer layout changes.
- No new public managed HTTP surface.
- No route availability semantics change.
- No attempt to make modules physically modular.

### Deliverables

- Capability schema.
- Capability response examples.
- Source/contract tests preventing collapse into one broad bridge bit.
- Domain inventory aligned with the roadmap.
- A minimal implementation plan for Phase 1 only.

### Domain Boundaries Touched

Phase 1 may observe all initial domains, but it must not move their
implementation boundaries. BIM/Rhino.Inside/Revit gets separate treatment
because host state, Revit API availability, active document state, and optional
assembly state are not just managed bridge readiness.

### Compatibility Invariants

- Existing route behavior is preserved.
- Existing startup behavior is preserved.
- Existing companion-load behavior is preserved.
- Existing installer layout and registry behavior are preserved.
- Existing clients can ignore the new capability surface.

### Validation Gates

- Source tests for domain inventory.
- Native discovery/capability source tests.
- Managed/source tests for companion-backed domain state where applicable.
- BIM/RhinoInside status-provider tests.
- MCP parsing tests if MCP consumes the contract in the same phase.
- Existing startup/GH/BIM/chat/vision behavior remains unchanged.
- Recent-file `_Open` live gate remains valid if runtime code changes touch
  startup/discovery.

### Rollback / Escape Hatch

Capability reporting can be removed, hidden, or ignored without changing route
behavior because Phase 1 must not alter execution semantics.

### Later Phases Must Not Assume Yet

- That errors are aligned with capability state.
- That installer module manifests exist.
- That runtime state can fully explain missing files.
- That on-demand loading is allowed.
- That any physical module layout has changed.

### Candidate PR Slices

1. Capability schema and source guards.
2. Native `/capabilities` plus discovery summary.
3. Managed domain status providers for companion-owned domains.
4. BIM/RhinoInside status provider boundary.
5. Optional MCP/client parser support.

## Phase 2: Diagnostics And Error Alignment

### Phase Goal

Make runtime failures name the same domains and reasons exposed by Phase 1
capability state.

### New Truth Introduced

Route failures and diagnostics can identify the responsible domain and reason
code instead of collapsing to generic bridge/runtime failure.

### Phase Exit Question

What can Rook truthfully say after Phase 2 that it could not say before?

Expected answer:

> When a domain operation fails, Rook can say whether the cause is host state,
> missing dependency, not loaded, not ready, degraded service health, missing
> credentials, future entitlement, or managed dependency unavailable.

### What Changes

- Align unavailable/degraded responses with capability domain IDs.
- Add stable reason codes for initial domains.
- Add domain-specific fields before replacing any legacy response shape:
  - `domain_id`
  - `reason_code`
  - `state`
  - `retryable`
  - `user_action_required`
  - `legacy_message`
- Make companion-backed block routes report `block.definition_mutation`, not
  vague GH bridge readiness.
- Make BIM failures report `bim.rhino_inside_revit` reasons such as:
  - `blocked_by_host`
  - `missing_revit_api`
  - `rookbim_assembly_missing`
  - `no_active_revit_document`
  - `managed_dependency_unavailable`
- Reserve stronger install-plane language such as `module_not_installed` for
  Phase 4, once manifest correlation exists.
- Make vision/media failures distinguish provider catalog, credential, artifact
  store, FFmpeg, job, and viewport capture problems.
- Make GH failures distinguish bridge availability from active canvas
  readiness.
- Make chat/UI diagnostics distinguish panel registration, chat service
  manifest, Python runtime, and service health.

### What Explicitly Does Not Change

- No route ownership changes.
- No loading-policy changes.
- No installer path changes.
- No new module manifest requirement.
- No new public managed surface.
- No physical modularization.
- No client-breaking response replacement in the first alignment pass.

### Deliverables

- Domain reason-code catalog.
- Additive error response alignment rules.
- Tests proving representative route failures use domain-specific reason
  codes.
- Updated troubleshooting/support text where appropriate.
- Phase 2 implementation plan or plans, written only after Phase 1 has landed
  and been reviewed.

### Domain Boundaries Touched

Phase 2 may touch response construction and diagnostic messages for GH, BIM,
chat/UI, vision/media, viewport capture, and companion-backed block exceptions.
It must not move execution ownership for those domains.

### Compatibility Invariants

- Existing success responses remain compatible.
- Existing failure consumers get legacy-compatible fields while new domain
  fields are added.
- Direct HTTP, MCP, and chat clients can migrate independently.

### Validation Gates

- Route contract/source tests for representative failures.
- Existing successful route behavior remains compatible.
- GH no-phantom-canvas gates remain intact.
- BIM standalone and Rhino.Inside/Revit gates remain intact.
- Vision credential/dependency failure tests where available.
- Chat service manifest/health tests where available.

### Rollback / Escape Hatch

If an aligned diagnostic causes client incompatibility, keep route behavior but
fall back response fields behind compatibility aliases. Do not remove the
domain state contract.

### Later Phases Must Not Assume Yet

- That installer module manifests exist.
- That every missing dependency can be traced to install evidence.
- That path layout can move.
- That loading policy can change.

### Candidate PR Slices

1. Reason-code catalog and response schema.
2. GH and block exception error alignment.
3. BIM/RhinoInside/Revit error alignment.
4. Vision/media/viewport error alignment.
5. Chat/UI/service diagnostic alignment.
6. MCP/chat client message consumption.

## Phase 3: Installer Module Manifest And Productization

### Phase Goal

Make the install plane explicit without reorganizing physical layout.

### New Truth Introduced

Installer/local deploy can report which product modules were installed, where
their current payloads/configs live, and which runtime domains they claim to
serve.

### Phase Exit Question

What can Rook truthfully say after Phase 3 that it could not say before?

Expected answer:

> Rook can distinguish "this product part was installed at this path/config"
> from "runtime says this domain is usable," even before full runtime/install
> correlation exists.

### What Changes

- Add installed module manifest generation to installer/post-install and local
  deploy.
- Record current-layout module evidence for:
  - `rook.native`
  - `rook.companion`
  - `rook.bim`
  - `rook.mcp`
  - `rook.chirp`
  - `rook.knowledge`
  - `rook.chat_service`
  - `rook.ffmpeg`
  - `rook.licensing` as reserved/future if useful
- Record module ID, version, payload path, runtime/framework, domains served,
  expected health probe/status location, upgrade/uninstall notes, diagnostic
  paths, validation result, and warnings.
- Extend release/local deploy validation to assert manifest shape and current
  paths.

### Manifest Provenance

Every manifest should include:

```text
schema_version
product_version
created_by: installer / local_deploy / dev
created_at
install_root
runtime_root
module records
validation result / warnings
```

The manifest records install evidence, not runtime health. It can say:

```text
module installed: yes
payload path: ...
serves domains: [...]
health_probe: /capabilities#vision.media
```

It must not say:

```text
vision.media is ready
```

Runtime state remains the authority for readiness.

### What Explicitly Does Not Change

- No installer path moves.
- No registry model change.
- No per-user to machine-wide registration change.
- No MSI/WiX migration.
- No runtime dependence on the manifest for basic route behavior.
- No automatic module loading changes.

### Deliverables

- Module manifest schema.
- Installer/post-install manifest writer.
- Local deploy manifest writer.
- Release guard tests.
- Installed-runtime validation updates.
- Phase 3 implementation plan or plans, written only after Phase 2 has landed
  and been reviewed.

### Domain Boundaries Touched

Phase 3 touches installer/local deploy/release validation and installed product
metadata. It may name runtime domains served by modules, but it does not change
runtime behavior for those domains.

### Compatibility Invariants

- Current physical layout is preserved.
- Current registry model is preserved.
- Current MCP/client config behavior is preserved except for additive manifest
  evidence.
- Existing installs without the manifest remain diagnosable as older installs.

### Validation Gates

- Release installer guard tests.
- Post-install validation.
- Local deploy installed-runtime gate.
- Release artifact validation.
- Upgrade/uninstall smoke where available.
- No source/worktree leakage into installed module records.

### Rollback / Escape Hatch

If manifest generation fails, installation should either fail clearly at
validation time or mark manifest generation failed in post-install diagnostics.
It must not silently claim modules are installed without evidence.

### Later Phases Must Not Assume Yet

- That runtime state consumes module manifest data.
- That every runtime domain can explain missing dependencies from install
  records.
- That physical layout has changed.
- That optional modules can be separately installed/uninstalled.

### Candidate PR Slices

1. Module manifest schema and fixture tests.
2. Post-install manifest generation.
3. Local deploy manifest generation.
4. Release guard and artifact validation updates.
5. Documentation/troubleshooting updates.

## Phase 4: Runtime / Install Correlation

### Phase Goal

Connect runtime capability state to installer module evidence so Rook can
explain whether a failure is caused by host/runtime state, missing payload,
stale install, bad config, missing dependency, or service health.

### New Truth Introduced

Runtime domains can reference install evidence, but they do not require path
moves or ownership changes.

### Phase Exit Question

What can Rook truthfully say after Phase 4 that it could not say before?

Expected answer:

> For a domain such as BIM, vision, chat, MCP, or knowledge, Rook can explain
> whether the domain is unavailable because the host is wrong, the runtime is
> not loaded, a payload is missing, a module record is absent/stale, a config
> points to the wrong place, a sidecar is missing, or a dependency is unhealthy.

### What Changes

- Runtime capability state may reference installer module records.
- Missing-dependency states can distinguish runtime absence from install
  absence where evidence supports it.
- `rook doctor`, release validation, and support diagnostics can compare
  runtime state against install evidence.
- Client-facing diagnostics can point to install evidence when useful.
- Domain state may include install evidence references:
  - module ID
  - manifest path
  - payload path
  - version
  - validation warnings
  - expected diagnostic/health probe
- Client config drift becomes first-class, including:
  - Claude/Codex/Cursor/VS Code MCP config points to stale runtime path;
  - chat service manifest points to a missing executable;
  - knowledge store path exists but version/hash does not match manifest;
  - MCP runtime path differs from installed module record.

### Manifest As Evidence, Not Authority

Manifest data must not assert runtime readiness. It is evidence used to explain
runtime state.

Allowed:

```text
runtime_state: missing_dependency
install_evidence: rook.ffmpeg installed at C:/...
correlation: payload_missing_or_moved
correlation_confidence: confirmed
```

Allowed:

```text
runtime_state: blocked_by_host
install_evidence: rook.bim installed
correlation: install_ok_host_blocked
correlation_confidence: confirmed
```

Not allowed:

```text
runtime_state: ready
because manifest says installed
```

Correlation confidence values:

```text
confirmed
partial
absent
stale
conflicting
```

### What Explicitly Does Not Change

- No route ownership changes.
- No companion loading-policy changes.
- No installer path moves.
- No registry model change.
- No automatic optional-module loading changes.
- No assumption that every domain has perfect install correlation.

### Deliverables

- Runtime/install correlation contract.
- Manifest reader/validator for support/runtime diagnostics.
- Domain-specific correlation for high-value domains first:
  - BIM/RookBIM
  - chat service
  - vision/media/FFmpeg
  - MCP runtime
  - knowledge stores
- Doctor/release validation updates.
- Phase 4 implementation plan or plans, written only after Phase 3 has landed
  and been reviewed.

### Domain Boundaries Touched

Phase 4 touches the boundary between runtime domain state and installed product
evidence. It should start with domains where correlation has clear support
value: BIM, chat service, vision/media/FFmpeg, MCP, knowledge, and Chirp.

### Compatibility Invariants

- Runtime availability must not depend on manifest correlation unless a later
  phase explicitly permits it.
- Domains remain discoverable when install evidence is absent or stale.
- Manifest absence is diagnostic information, not a route failure by itself.

### Validation Gates

- Missing/stale manifest tests.
- Missing payload tests.
- Wrong-path/local-deploy leakage tests.
- Runtime domain state still works without a manifest, but reports limited
  evidence.
- Release smoke includes capability plus module evidence.
- Upgrade/uninstall validation covers manifest lifecycle.

### Rollback / Escape Hatch

If manifest correlation is unreliable, runtime capability state must fall back
to runtime-only evidence and mark install evidence as unavailable, stale, or
conflicting.

### Later Phases Must Not Assume Yet

- That physical layout has changed.
- That route ownership can move.
- That on-demand loading is allowed.
- That all modules are independently installable.
- That entitlement/licensing gates can enforce behavior.

### Candidate PR Slices

1. Manifest reader and stale/missing handling.
2. BIM/RookBIM runtime/install correlation.
3. Chat service/runtime correlation.
4. Vision/media/FFmpeg correlation.
5. MCP/knowledge/Chirp correlation.
6. Doctor/release validation support bundle expansion.

## Phase 5: Selective Structural Change Eligibility

### Phase Goal

Allow carefully chosen structural changes only after state, diagnostics,
install evidence, and validation gates exist for the affected domain.

### New Truth Introduced

A domain may change loading, path layout, route ownership, or module packaging
only after it can prove its current and new states.

### Phase Exit Question

What can Rook truthfully say after Phase 5 that it could not say before?

Expected answer:

> For a specific domain, Rook can prove both the old and new behavior
> boundaries, explain the changed loading/ownership/layout decision, and
> validate that external clients still discover and handle the domain correctly.

### What Changes

Only domain-specific changes explicitly approved by a later implementation
plan. Possible eligible categories:

- selective on-demand loading;
- physical module path migration;
- optional module install/uninstall boundaries;
- route ownership movement;
- managed callback slot separation;
- paid/entitled module activation;
- enterprise installer variant.

### Domain Eligibility Checklist

No structural-change plan may start for a domain unless this checklist is
satisfied:

```text
capability state exists
diagnostics aligned
install evidence exists if packaging is involved
live gates exist
client discovery behavior verified
rollback/migration path defined
current availability semantics documented
```

No checklist, no structural-change PR.

Public route identity and client contract remain stable unless explicitly
versioned. A route can move internally only after the external route contract is
protected.

### What Explicitly Does Not Change

- No global companion-loading rewrite.
- No broad "modularization" PR.
- No physical layout migration without upgrade/uninstall validation.
- No route movement without compatibility and fallback behavior.
- No hiding domains when optional/unavailable.
- No replacing RookNative as public HTTP/discovery surface.

### Deliverables

- Per-domain structural-change proposal.
- Before/after capability contract.
- Compatibility and rollback plan.
- Live validation gates.
- Upgrade/uninstall path when packaging changes.
- Phase 5 implementation plan per domain, not one mega-plan.

### Domain Boundaries Touched

Only the selected domain's boundaries are touched. Phase 5 does not grant
blanket permission for other domains.

### Compatibility Invariants

- Existing Phase 1-4 state/diagnostics/install gates still pass.
- Existing availability semantics are preserved or explicitly versioned.
- External clients can continue to discover domain state before acting.
- Public route identity remains stable unless a versioned contract change is
  explicitly approved.

### Validation Gates

- Existing Phase 1-4 state/diagnostics/install gates still pass.
- Domain-specific live tests pass.
- Existing availability semantics are preserved or explicitly versioned.
- External client discovery behavior verified.
- Rollback path tested.
- Release installer and local deploy validation pass.

### Rollback / Escape Hatch

Every structural change must be reversible or compatibility-preserving. If a
change cannot be rolled back without breaking installed users, it needs a
migration/versioning plan before implementation.

### Later Phases Must Not Assume Yet

Phase 5 does not create a new blanket permission phase. Each domain earns
eligibility independently.

### Candidate PR Slices

1. Pick one domain and write a structural-change spec.
2. Add missing validation gates for that domain.
3. Implement the smallest reversible structural change.
4. Validate live and release paths.
5. Repeat only if the first domain proves the pattern.

## Cross-Phase Review Checklist

Every PR derived from this roadmap should declare:

```text
phase touched
plane touched: behavior / state / install / correlation
domains touched
new truth introduced
availability semantics changed: yes/no
route ownership changed: yes/no
installer paths changed: yes/no
loading policy changed: yes/no
client-visible contract changed: yes/no
schema/version changed: yes/no
live gates skipped: yes/no + reason
validation gates run
rollback/escape hatch
```

If a PR says "no behavior change," reviewers should be able to confirm that
from route behavior, startup behavior, installer layout, and client-visible
output.

## State Truth Rule

Capability state must be derived from evidence:

```text
real runtime probes
registered callbacks
current host state
known unavailable providers
direct file/config checks
installer module evidence where the phase permits it
```

It must not become a hand-maintained second truth.

## Handoff Rule

This spec authorizes only the Phase 1 implementation plan immediately.

Do not write Phase 2 through Phase 5 implementation plans until Phase 1 has
landed and been reviewed. Later phase plans must be informed by evidence from
earlier phases.

The next artifact should be:

```text
docs/superpowers/plans/YYYY-MM-DD-rook-ecosystem-phase-1-capability-discovery.md
```

That plan should use the `superpowers:writing-plans` workflow and should cover
only Phase 1.

## Final Review Position

The roadmap is safe only if execution order remains the safety mechanism:

```text
Phase 1: say what exists and what state it is in
Phase 2: make failures speak that same language
Phase 3: make installation evidence explicit
Phase 4: correlate runtime state with install evidence
Phase 5: consider domain-specific structural changes
```

The first real architectural shift is not modularization. It is the move from
implicit coupling to explicit, evidence-backed state.
