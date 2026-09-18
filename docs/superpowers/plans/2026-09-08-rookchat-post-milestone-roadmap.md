# RookChat Post-Milestone Roadmap

**Status:** Approved roadmap. Documentation only; no investigation, implementation, deployment or live execution is authorized by this document.

**Objective:** Move from a working developer installation to a dependable, supportable and explicitly qualified customer experience without replacing the ACP architecture or losing the working baseline.

## Starting Point And Authority

The [approved milestone](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/docs/superpowers/reports/2026-09-08-rookchat-working-dev-milestone.md), committed at `a0e048d3721cb942937534fc32226e16134cffd5`, is the baseline record. Preserving that note is complete, not a new roadmap task. It records a mixed-source developer installation, successful user-observed conversation, inspection and GH authoring, and the limits of those observations.

Accepted A+B and the bounded Slice C disposition remain accepted for their recorded identities and scope. Failed historical attempts remain failed. Neither informal GH authoring nor the image smoke result completes formal D/E or customer-release qualification.

This roadmap orders work; it does not replace the [ACP implementation plan](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/docs/superpowers/plans/2026-09-01-rookchat-prime-acp-replacement.md), its approved corrections, or its live execution boundaries. Use existing entrypoints and reviewed evidence when preparing each gate. Historical command examples are not fresh execution authority. Resolve a concrete conflict before execution, without reopening unrelated architecture.

## Sequence And Dependencies

| Phase | Outcome | Dependency / review boundary |
| --- | --- | --- |
| 1. Developer stability | Understand repeated progress and the shutdown hang; establish supported conversation continuity/recovery. | Start with the progress trace. Review diagnosis and recovery scope before a fix or live check. |
| 2. Customer onboarding | A reviewed installation-to-first-prompt journey, including account connection and model/reasoning selection. | Source-only preparation can proceed independently; implementation and real login require separate approval. |
| 3. Release candidate preparation | Explicit dependency-security disposition and a coherent installed product built from reviewed source. | Follow stability/onboarding changes intended for that candidate; approve promotion before execution. |
| 4. Slice D | Formal, read-only installed Rhino/GH qualification. | Accepted promotion identity, frozen fixture and explicit one-execution authorization. |
| 5. Slice E | Formal goal-driven GH authoring qualification. | Accepted D result, matching installed identities and separate execution authorization. |
| 6. Customer-release decision | Evidence supports precisely stated shipping and continuity/recovery claims. | Accepted applicable live gates, actual release payload, onboarding, recovery and security decisions. |

Security triage and onboarding design need not wait for a rare shutdown recurrence. A hang that cannot be reproduced remains explicitly unresolved, not silently closed. Before customer release, an unexplained hang needs an evidence-based disposition; waiting alone is not proof of resolution.

## Phase 1: Stabilize Developer Interaction

### 1A. Repeated Progress Text - Recommended First Task

**Observed:** The supplied transcript repeats accumulated progress paragraphs. It is not established whether the source is emission, projection, rendering or transcript extraction.

**First deliverable:** A bounded, read-only trace of one retained example through the existing ACP projection and panel renderer, identifying the earliest demonstrated duplication. If retained data is insufficient, report that limitation and propose the smallest capture; do not make another model call to fill the gap without approval.

**Subsequent scope, only after approval:** A local correction at the demonstrated owner, with a deterministic regression covering the real producer/consumer contract. Do not deduplicate arbitrary text heuristically or alter Prime's reasoning to conceal a presentation defect.

**Exit:** Cause established or uncertainty reported; any implemented correction has focused causal coverage. A separately authorized panel check confirms progress remains intelligible and final response delivery is preserved. Local tests alone do not establish installed-panel behavior.

### 1B. Rhino Shutdown Hang

**Observed:** Rhino remained in the background after the user closed its window. No retained stack establishes the cause or ties it to ACP.

**First deliverable:** On a recurrence and with authorization, capture one bounded diagnostic from the exact affected Rhino process before termination. Trace the blocked owner/call path; do not infer a leak from a process name or add monitoring, kill loops, timeout inflation or speculative cleanup.

**Exit:** A concrete cause and focused correction/verification, or an explicit unresolved-risk disposition. A disappeared process is not evidence of a fix. Any live shutdown check is separately authorized.

### 1C. Conversation Continuity And Recovery

**Open question:** Working conversation does not establish the customer experience after normal close/reopen, service or machine interruption, a retained `open.claim`, or an unavailable or changed Rhino/document binding. Do not assume the shutdown hang and these cases share a cause.

**First deliverable:** A bounded review of existing behavior and evidence for each case, distinguishing durable Prime history, Rook's association/ownership state and the current Rhino/GH document. Propose which user actions are supported, which conditions require support, what diagnostic information is safe to collect, and what must refuse. Identify missing proof without designing a replacement recovery system.

**Exit:** An approved continuity/recovery scope with customer-visible outcomes, supported user/support actions and identified verification gaps. No automatic mutation replay, silent rebinding or assumed manual lock deletion workflow. Uncertain ownership must not become permission to reclaim a retained claim. Actual recovery design, tests and live checks require separate authorization.

Carry this workstream through candidate preparation and the Phase 6 release decision. Normal reopening and honest refusal/support behavior are distinct from restoring a Rhino document or guaranteeing recovery of in-flight work.

## Phase 2: Complete First-Use Journey

**Observed:** Reviewed developer OAuth succeeded; that manual source-based procedure is not a shipped customer experience.

**First deliverable:** Map the complete customer journey: installation -> account connection -> model/reasoning selection -> first prompt. Trace the available shipped sign-in entrypoint through executable dependencies and credential destination to the actual ACP consumer. Specify customer-visible defaults and configuration, how requested versus effective model/reasoning choices are communicated, returning-user behavior, and cancellation/failure outcomes. Include truthful first-use preparation feedback so account connection, preparation, readiness and prompt failure are not conflated. Do not inspect credential contents or assume catalog presence means account access.

**Design boundary:** Prefer existing supported Prime interfaces; Prime owns credentials and effective model settings, while Rook presents the supported choices and outcomes. Investigate the pinned interfaces before promising model/reasoning changes mid-conversation. If the frozen runtime cannot support customer onboarding, return that product decision for review rather than silently adding a launcher, copying credentials or expanding the Prime patch.

**Exit:** An approved installation-to-first-prompt procedure/UI with explicit defaults, preparation feedback and returning-user behavior; its credential writer and consumer use the same intended store. Subsequently authorize direct-user authentication and bounded first-prompt verification separately. Credentials stay outside evidence and cleanup targets. Developer login and a successful model response alone must not be presented as proof of complete onboarding.

## Phase 3: Prepare A Coherent Release Candidate

### 3A. Dependency And Reliability Disposition

Use existing retained audits and release records to distinguish already-closed pip bootstrap/downloader corrections from outstanding Prime/package findings. Where fresh diagnosis is required, prepare the existing separately authorized bounded audit, not automatic dependency repair.

Record affected package/advisory, shipped scope, reachability, patched-version availability and an explicit remediate/defer/accept decision. An unmitigated runtime-relevant high-severity finding blocks customer release. Do not reopen a closed finding without new evidence or treat a passing build as security approval.

Retain the recorded false-UTC build-diagnostic correction as a prerequisite before any future Prime build. Retain the deferred bounded-kernel-stderr reliability risk in its existing qualification context. Neither item authorizes a rebuild or a new lifecycle system; a necessary Prime/dependency change requires its own review and affected qualification scope.

### 3B. Installed Product And Release Payload

The current managed/Python developer configuration is intentionally mixed. After the changes intended for a release candidate are reviewed, prepare the existing promotion workflow from one clean selected source, with explicit Chirp selection, the selected fresh wheelhouse verifier, normal deployment blockers and built-to-installed byte comparisons.

Resolve the unresolved knowledge-file modification through a separate user disposition before any gate requiring a clean source tree. Do not restore, stage, delete or attribute it as part of roadmap execution.

**Exit:** Independently reviewed installed-byte evidence for the candidate, with release Python rather than checkout-backed imports. Preserve the accepted Prime runtime unless a separately reviewed change requires otherwise. Use existing build/deploy/installer entrypoints; no alternate deployment manager or manifest. Real Release outputs and the full installer guard remain required where the existing release workflow requires them.

A prior promotion or verification-only follow-up is evidence for its recorded bytes, not proof that subsequent dev changes are a qualified release. Rebuild only what the selected release workflow and changed source identity require; do not rerun unrelated Prime or accepted A+B/C work automatically.

## Phase 4: Formal Slice D - Read-Only Integration

Use Task 12 Step 10: one frozen Rhino/GH fixture and read-only prompt, exact target/profile, reverified installed identities and service origins, before/after structural observations, and absence of mutation receipts. Keep model-free reopen/denial controls separate from the single stochastic prompt.

**Exit:** One authorized execution, honest sealed result and independent acceptance before E. Installed drift refuses before contact. Informal inspection from the milestone is supporting experience, not a substitute for this gate.

## Phase 5: Formal Slice E - Goal-Driven Authoring

Use Task 12 Step 11 and its established adjustable X-axis point-row defect. Freeze prompt, model/reasoning, evaluator, identities and bounds. Preserve the existing chain from the last actual mutation/restoration receipt through readiness and fenced observation to `goal.complete()`, final text and settlement. Keep the silent evaluator separate; its actions cannot satisfy the actor's criteria.

**Exit:** One authorized execution with an accepted result or an honestly incomplete outcome. No prompt repair, automatic mutation replay or retry of a consumed frozen version. Report observable geometry/goal evidence, not the model's claim alone.

## Phase 6: Customer-Release Decision

Review the actual release candidate against the existing release workflow and accepted evidence. Require explicit disposition of onboarding, dependency security, shutdown reliability, conversation continuity/recovery, installation/upgrade/retention behavior and all applicable live qualification. Validate the real packaged payload, not just a developer deployment.

Make a specific continuity/recovery release decision for normal close/reopen, service or machine interruption, retained `open.claim`, and unavailable or changed Rhino/document bindings. For each, record the verified outcome, supported user/support action and any explicit limitation or release blocker. Do not ship an implied recovery promise whose practical instruction is manual lock deletion, silent rebinding or replay of uncertain mutations. This decision does not require universal restoration guarantees.

Keep claims narrow: D/E text/tool success does not establish a live panel-to-model image round trip or general vision reliability. If live panel image support is to be claimed, its missing proof requires a separately scoped decision and authorization, not an inference from C or E.

**Exit:** A documented ship/hold decision identifying supported configuration, accepted limitations and outstanding exclusions. This roadmap does not promise a date or turn incomplete evidence into release readiness.

## Deferred Work

Visible follow-ups, not mandatory additions to these six phases unless a concrete release blocker establishes their necessity:

- Upstream Prime refresh and patch-series maintenance beyond required security/reliability disposition.
- Richer model controls, including mid-conversation switching beyond the supported first-use selection established in Phase 2.
- Conversation archive and explicit rebinding experiences beyond honest current binding/refusal behavior.
- Stronger restoration guarantees for documents, interrupted operations or historical environments beyond the approved continuity/recovery scope.
- Richer attachment-history browsing and reuse beyond existing persistence and separately claimed image behavior.
- Old-runtime cleanup/retention automation; no deletion is authorized and recorded conversation dependencies must remain respected.

Deferral does not waive an existing safety contract, required security correction or unsupported shipping claim. Each item needs a separate product decision before becoming implementation scope.

## Working Rules

- Use [managed-only and Python-dev iteration](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/.agents/skills/deploy-local-testing/SKILL.md) for compatible local changes. Do not require a full release build for every UI/Python edit. Dev setup still has its documented sync effects; it is not release qualification.
- Within an authorized correction, iterate bounded model-free tests normally. Preserve evidence of actual defects; do not turn every ordinary local test failure into a new qualification version. Frozen live attempts retain their existing one-execution and review stops.
- Preserve unrelated installed payloads, Prime/runtime identity, authentication, persistent data, accepted/failed evidence and the unresolved knowledge note. Do not claim historical evidence automatically covers changed behavior; review only the affected proof scope.
- RookChat owns presentation and conversation/process association; the official SDK owns ACP transport; Prime owns reasoning and conversational state; Rook owns Rhino/GH operations and authority.
- Add no private Prime protocol, duplicate reasoning loop, automatic mutation replay, general policy engine or new process-ownership framework. New machinery requires a demonstrated need, not speculative assurance.

**Immediate proposed authorization:** Phase 1A's read-only repeated-progress trace only. All implementation, process diagnostics, authentication, deployment and live qualification remain separate decisions. No roadmap work has been executed by writing this document.
