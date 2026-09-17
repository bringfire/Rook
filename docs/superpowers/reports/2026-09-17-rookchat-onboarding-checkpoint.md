# RookChat Onboarding Checkpoint

**Status: DRAFT for independent review.** User-observed working account connection and text conversation, not comprehensive first-use or customer-release qualification. Read-only snapshot began **2026-09-17T04:58:53Z** (00:58:53 EDT). The source identities below precede this documentation-only draft. This note authorizes no execution.

## What the user observed

The user connected their ChatGPT account through RookChat's Settings and the provider authorization page. RookChat reported configuration saved and configuration-process exit 0; subsequent status displayed the dedicated route and an OAuth credential. The user saved **openai-codex/gpt-5.6-sol, reasoning high**, closed/reopened Settings, and saw those saved values read back. A new conversation then reported those same effective settings. The user submitted "Reply with hello only. Do not use tools", received **hello**, and saw the panel return to **Ready**. The user subsequently reported closing Rhino.

This sequence used no separate Prime terminal or customer environment-variable setup. It followed operator-led installation and explicit repair of this machine's existing exposed store; it does not establish an unaided fresh-customer journey. The provider name, OAuth presence, saved settings and reported effective settings do **not** identify the billed account or prove a particular subscription/billing route. The visible response supports one live text round trip, not universal model access, reliability, or independent proof that no tools executed.

User-supplied evidence, referenced in place:

- [Account connection save/exit confirmation](C:/Users/bring/AppData/Local/Temp/codex-clipboard-aed382af-c608-464b-8271-4e1a1e3caec3.png).
- [Saved defaults after reopening Settings](C:/Users/bring/AppData/Local/Temp/codex-clipboard-d2f19b64-3c57-427c-9e96-b41ec589d797.png).
- [New conversation reporting the chosen settings](C:/Users/bring/AppData/Local/Temp/codex-clipboard-a00c07af-837e-45db-8211-5b1c42a14a68.png).
- [Live hello response and Ready state](C:/Users/bring/AppData/Local/Temp/codex-clipboard-db2b50c7-8807-41a4-b8a2-8022110769e6.png).

These are user observations/screenshots, not a new instrumented qualification. Their local temporary files exist at this snapshot; they were not copied. They and the local evidence below are unavailable from a repository clone alone, and temporary screenshots may later disappear. No credential or conversation-data backup was created.

## Installation at the snapshot

| Component | Identity and basis |
| --- | --- |
| Rook implementation checkout | `C:/UDEV/Rook/.worktrees/rookchat-configuration`, HEAD **bee39bc72d66b86ab9cdd8e8a3698b9aa2afe9b4**, clean before drafting; verified now. |
| Prime implementation checkout | `D:/prime-agent/.worktrees/rookchat-configuration`, HEAD **dacbeab26b705e7d07b55ae6f8cd3e95ceb5458b**, clean; verified now. Installed runtime manifest declares this compatibility/source identity and upstream **c718bf3c30fd8da206ed551837cbb54f7ad15948**. |
| Installed Prime runtime | **83CAE9A047FBD3A30AC48328AB466AD1DF80D97C2798612DD04BEF06CFEDF513**, selected by `C:/Users/bring/AppData/Local/Rook/app/prime/current.json`. Current pointer and runtime-manifest hashes checked now; runtime-manifest SHA-256 equals the runtime ID. Whole-payload verification is historical evidence, not rerun. |
| Managed companion | Release `net8.0`, `net7.0`, `net48` built from the Rook identity above by the retained companion-only build; build exit 0, zero errors, 465 warnings. All six installed RHP/PDB hashes match both retained successful comparisons and current checkout outputs now; exact hashes below. |
| Python release payload | Version **1.5.18**, manifest declares Rook **bee39bc72d66b86ab9cdd8e8a3698b9aa2afe9b4** and Chirp **1f954c27f796ecfe830d02a76497deffcf31cfc2**. Installed and retained staging manifest SHA-256 both **1E431C83502D2A601557B24694C471C62372BC81FE4EDFA35631811303A01785**, checked now. V4 wheelhouse/build root was reused, not rebuilt for the continuation. |
| Chat mode and configuration | Root and all three runtime-child `RookChatService.json` files under `C:/Users/bring/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative` agree: **release**, owner `rhino-panel`, module `rook.agent.chat.service_main`, empty `pythonPathEntries`. Each hash is **69E01F7684C348AD8B07FBC6CE04AAAAE6D38F25E81DBA658A93800A0BB42151**, checked now. This is not Python-dev mode. |
| Installed interpreter and source | `C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe`, SHA-256 **21BB438C0D4A6F1F164B9A646F6EE000340185E5871180AEC06DB8D3F07C0082**. Retained installed verifier resolves Rook/service imports under that venv's `Lib/site-packages/rook`. Current `__init__.py`, `agent/chat/service_main.py` and `agent/chat/configuration_storage.py` bytes match checkout source; imports were not executed now. |
| App, cwd and persistent roots | App/Prime root: `C:/Users/bring/AppData/Local/Rook/app` and its `prime` child. Chat cwd: `<app>/mcp_server`. Data: `C:/Users/bring/AppData/Local/Rook/data`; dedicated configuration binding: `<data>/prime-config`. On-disk nonsecret launch metadata only, not inspection of a running process environment or store contents. |
| Native/BIM and Chirp | Native/BIM outputs reused from the earlier installed build at Rook **616c3fa3503f063c4474adc1880042f4d5da5034**; retained continuation admission checked unchanged source trees and exact reused bytes. They were not rebuilt at bee39bc7. Chirp checkout `C:/UDEV/Chirp` is clean at **1f954c27f796ecfe830d02a76497deffcf31cfc2**, verified now; installed Chirp comparisons are historical. |

Current installed managed SHA-256 values:

| Target | Rook.rhp | Rook.pdb |
| --- | --- | --- |
| net8.0 | `657217CABC3DEE4DE2C7D6510806316E9555888707822B3692470A33D18D027E` | `6EB4A375C9C95BD3E2D66D220907EB6A9BA09B855D5FE048D06381BA8198D58A` |
| net7.0 | `C82F0B86890B5EEA58FE38F9EB07EA10524AEFEC9CA751A86CD68BB5AF3C5BAC` | `362988A43CDDCC3DBFA6A61C86DB60E59A620943585C2934318E98A9EA6F9C2E` |
| net48 | `D168921368928884820E0095A3740BFB184DDC57E57BC70C83CC57D5DD2C9746` | `1468E96A947A4C81FA7F4601CE54A1440D2549E66D7523D69FAFCDB2CA038152` |

**Differences and limits:** no discrepancy found in the selected current-byte checks. This is not a new complete installed-file comparison or a claim that every component was rebuilt at current HEAD. The original developer checkout `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset` remains at **5bdd694308af7173b95fa6d99950d931db0e275f**, with only the unresolved, unstaged `knowledge/gh/notes/teaching_4f2b9009.json` modification. It is not the current release chat source. That file was not inspected, attributed, modified or staged.

## Existing verification and protection evidence

- [V4 result](C:/UDEV/RookQualification/rookchat-configuration-promotion-v4/result.json): **failed before deployment** when Rook processes reappeared. The fresh 107-wheel wheelhouse, temporary installs, both audits under the existing exception policy, and wheelhouse validation had passed. This failed seal remains unchanged.
- [Deployment continuation](C:/UDEV/RookQualification/storage-deploy-continuation-v1/result.json): companion-only build, full deployment with `-SkipBuild`, installer guard and installed verifier all exited 0. The overall record remains **failed** at final comparisons because three old managed PDBs remained installed. No native, BIM, wheelhouse or Prime rebuild occurred in this continuation.
- [Managed copy and final verification](C:/UDEV/RookQualification/storage-managed-copy-verification-v1/result.json), [183 exact comparisons](C:/UDEV/RookQualification/storage-managed-copy-verification-v1/installed-comparisons.json), [installed identity](C:/UDEV/RookQualification/storage-managed-copy-verification-v1/installed-identity.json): existing `-ManagedOnly -SkipBuild` copied the RHP/PDB pairs; all final comparisons passed. Seven direct child exits were observed at 0, with no timeout or overflow; descendant settlement was not independently observed. Result SHA-256 **8FB549C3687955938E23FF0B91D57DC8934994A4B2216AB7F8291186F402E98E**; index **1284F4E26981CDF6DFAF625C899043C674182CEF38517D68333FA74D2017F628**, rechecked now. Full payload preservation of the current and two historical Prime generations is supported by that prior execution, not rerun here.
- [Installed storage repair/privacy result](C:/UDEV/RookQualification/installed-storage-repair-v1/result.json): the unelevated installed helper reported `repaired/ok`, `admission=passed`, `cleanup=closed`, observed exit 0, no timeout/overflow and no stderr. Permissions were corrected on the existing owned directory and auth file; identities were retained, and missing optional settings/model files stayed absent then. No ancestor repair, credential-content access or migration was part of that operation. Result SHA-256 **F5221A2467104F66AAC2CF23B9FE34BE0A9982B217BEFE911CAF71E7DC00EF8E**; index **E245544B41C448FCD85F8BD77CE8BB5600F9406F3004D9F568964B6A49F42FC5**, rechecked now. This precedes subsequent user login/default writes; current ACLs and credential contents were not inspected for this note.
- [Storage source-review evidence](../../../artifacts/rookchat-configuration/storage-repair-source-review.md) records 351 passing cases, including 39 storage cases, with synthetic writer/replacement/refresh coverage. Historical tests only. Prior managed evidence retains its separate-host limitation. Installed helper SHA-256 **660C82EF34D54DE032FE5CE3E7794E4463016ABA1E0C0686D1598EA4B855C9CC** matches current source and retained deployment identity now.

Result/index hashes and seal-marker presence were checked now; this documentation task did not revalidate every indexed evidence file or execute a verifier. These local qualification/artifact directories are not part of a repository clone. The later successful records supplement, and do not relabel or supersede, the earlier failed attempts.

## Remaining work and non-claims

- **First-use guidance:** the user reports the first failed turn occurred before setup was complete, with no useful direction to Settings. [Failed-turn screenshot](C:/Users/bring/AppData/Local/Temp/codex-clipboard-e9928c32-2ad0-4a49-94ac-91842a724e50.png). The exact failure cause is unresolved; missing saved defaults alone does not prove it, because Prime has fallback selection. Do not retain the earlier speculative account/conversation timing explanation as a diagnosis.
- **Truthful errors and recovery:** "Prime ready" followed by generic "Prime turn failed" did not explain the required action. Recovery across setup, failed turns, cancellation and close/reopen remains to be tested; a successful new conversation does not prove recovery of the failed one. No automatic prompt/mutation replay is implied.
- **Settings presentation:** clipped Close button, stretched controls, blank provider/model/reasoning selections on refresh/reopen, and loading models selecting the first catalog entry rather than the displayed saved default remain UI issues. Saved defaults and last-reported effective session settings must stay distinct.
- **Reported freeze:** the user reported the attachment **+** freezing the panel once; later it opened a file browser after setup. [Marked control](C:/Users/bring/AppData/Local/Temp/codex-clipboard-929cca59-512d-4eaf-b68c-8f215d19bc1c.png). A hidden/modal file dialog, blocked UI and setup/failure-state interaction remain hypotheses. No reproduction, stack or causal link was established. The older Rhino shutdown-hang report is also not resolved by this milestone.
- **Release/security:** the [retained dependency triage](../../../artifacts/rookchat-configuration/task8-dependency-security-review.md) leaves shipped `extract-zip` unresolved, with an explicit customer-release risk decision pending. Scoped ACP/configuration non-reachability is not absence, a patch or an OS sandbox. Tooling maintenance and the existing Python advisory exception/mitigation remain separate; no fresh audit or security clearance is claimed.
- **Qualification:** formal D/E, broader customer onboarding/recovery, customer installer/release readiness and live panel-image behavior remain unqualified by this text result. Accepted earlier A+B/C evidence and all failed evidence retain their original scope and disposition; this milestone replaces none of them.

## Stop boundary

Only this draft note was created. No tests, builds, deployment, runtime launch, process inspection/termination, prompts, login, credential-content reads/copies/hashes, ACL/configuration changes, conversation cleanup or runtime removal occurred. Existing screenshots/evidence were referenced in place. No staging, commit, tag or next task is authorized or performed. Preserve the working installation, pinned Prime runtime, historical configuration/conversation bindings and unrelated worktree changes pending review.
