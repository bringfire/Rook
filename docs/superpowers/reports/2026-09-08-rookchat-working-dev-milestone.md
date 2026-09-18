# RookChat Working Developer Milestone - Handoff

**Status:** Approved milestone record of a working, mixed-source developer installation; not a qualified customer release. Read-only identity snapshot: 2026-09-09T01:32:25Z (September 8 local time). The baseline HEAD below identifies that snapshot, not the subsequent documentation-only commit containing this note. No tests, builds, process inspection, runtime launches, configuration changes or qualification execution were performed for this note.

## Baseline Verified At Snapshot

| Component | Observed identity/state |
| --- | --- |
| Rook checkout | `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset`, HEAD `ec6eeddb15dd006fea8115253aa0be4eb0dfc1ec` |
| Rook status before drafting | No staged changes or untracked files; one tracked modification: `knowledge/gh/notes/teaching_4f2b9009.json`. Unresolved, not inspected for cause, restored, staged or otherwise modified by this task. This note alone is included in the subsequent documentation commit. |
| Installed managed companion | Retained deployment identifies source `2aeb3cbce68352b9028199fc7b37f7c539618095`. All six installed `Rook.rhp`/`Rook.pdb` files across `net8.0`, `net7.0`, `net48` currently match that record's SHA-256 values. Build provenance is retained evidence, not a new build. |
| Plugin root | `C:/Users/bring/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative` |
| Chat configuration | Root and all three runtime-child `RookChatService.json` files agree: `dev`, module `rook.agent.chat.service_main`, owner `rhino-panel`. Each file SHA-256: `91D86C38502F0E7E8F2E314EAD373EDCA78D3A30F2F23A4618DA41BAF129DD39`. |
| Interpreter | `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe` (exists) |
| Source / working directory | Sole source entry: `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/src`; working directory: `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server`; project root is the Rook checkout. |
| Installed app / Prime root | `C:/Users/bring/AppData/Local/Rook/app`; Prime remains beneath its `prime` directory. |
| Persistent data | `C:/Users/bring/AppData/Local/Rook/data`; canonical ACP data remains under `rookchat/acp/v1` there. |
| Prime checkout | `D:/prime-agent/.worktrees/rookchat-prime-final-series`, HEAD `b71badc503f650cd7c10c4acd1206a8406aa0a0b`, clean |
| Prime runtime | Installed `current.json` selects `4BFA4A0500FECEAAEC737563623521562C5F4FDF2592EA443C956E0063A12579`; runtime lives at `<Prime root>/runtimes/<ID>`. Its current manifest SHA-256 equals that ID, declares the same Prime commit, and lists 265 files. |
| Chirp checkout | `C:/UDEV/Chirp`, HEAD `1f954c27f796ecfe830d02a76497deffcf31cfc2`, clean. Installed Chirp path remains `C:/Users/bring/AppData/Local/Rook/app/chirp`; installed Chirp bytes were not requalified here. |

These are on-disk launch settings, not inspection of any running process's environment. Successful checkout imports and complete Prime payload verification are supported by the retained deployment record; neither was executed again. The current manifest hash check alone is not a new full payload verification. Native, release-Python and other installed payloads must not be described as newly built from current Rook HEAD.

**Discrepancies/caveats:** No discrepancy found against the recorded mixed-source identities. Rook is not clean because of the unresolved knowledge note. The dev deployment log's generic footer prints the release interpreter; its actual import probe and the four current manifests establish the checkout interpreter instead. Prior session metadata reported `openai/gpt-5.6-sol`, reasoning `medium`; model selection, credentials and billing route were not rechecked here.

## Retained Evidence And Observed Milestone

- [Managed deployment and review](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/managed-only-review/review.md), [installed-byte comparisons](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/managed-only-review/deployment-verification.json): successful three-target deployment; six changed companion files and 114 other plugin files unchanged at deployment. Comparison-record hash rechecked: `5EDD72A65BCF8CFD65667FEEFAE092E2F603EC4B0CF8FA82C068DEA403E21593`.
- [WebView callback correction](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/bridge-deferral-review/review.md), [metadata-card correction](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/session-metadata-review/review.md), [dev setup and execution](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/dev-runtime-review/review.md). The retained dev deployment log hash matches `037A44BE686C98E15EEC5E74B166795FB0ABB465350A91E73F2E5A3580844F65`.
- Existing regression reports: [managed-only: 29 passed](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/managed-only-review/tests.xml), [presentation: 96 passed](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/session-metadata-review/tests.xml), [dev paths/deployment: 38 passed](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/artifacts/dev-runtime-review/tests.xml). Historical results, not rerun; suites overlap. Referenced artifacts remain in their existing local locations, not copied into this note.
- [User-supplied live transcript](C:/Users/bring/.codex/attachments/38dcfaf0-383d-42a6-bd16-209340cdd040/pasted-text.txt): conversation replies, completed tool cards, reported inspection of a 37-object Rhino document and empty Grasshopper canvas, then reported creation of an editable 11-by-11 radial height field (121 boxes, six controls, no reported GH errors/warnings). The user confirmed it appeared to work. This is user-observed evidence, not independent geometry verification or a formal D/E qualification run.

Accepted A+B and the [bounded Slice C disposition](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/docs/superpowers/reports/2026-09-07-rookchat-prime-acp-slice-c-disposition.md) remain historical and unchanged. Customer onboarding, formal D/E qualification, complete release-payload qualification and release-security disposition remain separate. A live panel-to-model image round trip and general vision reliability are not established by this milestone.

## Iteration And Preservation Boundaries

Use the [existing deployment skill](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/.agents/skills/deploy-local-testing/SKILL.md) and [deployment script](C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/scripts/deploy-local-testing.ps1), not a parallel procedure. `-ManagedOnly` handles compatible C#/embedded-resource iteration. `-PayloadOnly -UseRepoVenv` enabled the current Python dev setup; subsequent Python-only edits require a new service process, not another release build. Setup still has documented AppData/Chirp sync side effects; dependency changes and release qualification are not covered by this shortcut. No command is authorized by this note.

For an unrelated correction, preserve the pinned Prime commit, installed runtime/pointer, authentication configuration, persistent sessions/associations/claims, native/BIM payloads, Chirp, dependencies and accepted/failed qualification evidence. Change only the implicated source layer; separately authorize tests, deployment and live checks. Do not alter the unresolved knowledge note. Do not normalize the mixed installation into a claimed single release identity.

Keep the established ownership: RookChat owns presentation and conversation/process association; the official SDK owns ACP transport; Prime owns reasoning and conversational state; Rook owns Rhino/GH operations and authority. No private Prime protocol, duplicate reasoning loop, automatic mutation replay, new process-ownership machinery, manifest or harness.

## Next Work - Proposed Only

| Issue | Symptom and unknown | Smallest next diagnostic |
| --- | --- | --- |
| Repeated progress text | The transcript repeats accumulated progress paragraphs. Unknown whether duplication originates in emitted chunks, accumulation, rendering or transcript extraction. | Read-only comparison of a bounded retained stream segment with the existing projection and renderer. Identify the first divergent representation; no model call or implementation yet. |
| Rhino shutdown hang | User reported background Rhino after closing its window. No dump/stack established the cause or a connection to ACP. | On a recurrence, separately authorize an exact-process hang dump before termination; no present monitoring, process scan or automatic cleanup. |
| First-time authentication/onboarding | Developer OAuth login succeeded through a reviewed manual procedure, but that is not shipped onboarding. Current credential/billing route is not established by this note. | Read-only trace of the shipped sign-in entrypoint through credential destination to the ACP consumer, excluding secret contents; identify the smallest missing user-facing step. |
| Remaining live/release qualification | Informal inspection/authoring worked, but formal D/E, full release payload, onboarding and security approval remain incomplete. | Review existing plans/evidence to select the next still-required bounded gate and its admission requirements; no new harness/version or execution. Preserve prior dependency findings and the recorded UTC-label correction required before a future Prime build. |

**Recommended next task:** investigate repeated progress text using that bounded, read-only producer-to-renderer trace. Return a concrete diagnosis and smallest proposed correction for review, without changing behavior or using another live model interaction. All other work stays separate. Stop here for independent review.
