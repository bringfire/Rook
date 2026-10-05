# Workforce federation verification

Implementation uses the approved MSAL public desktop and Google auth STS assertion contract. Credentials remain Python-owned, with DPAPI-protected persistence; workforce media reuses the existing RookVision providers, managers, ledger and artifact pipeline.

Automated implementation evidence and installed live acceptance are separate gates. Tasks 1–7 have focused source checks; exact fresh build/runtime/whole-branch results are recorded below after Task 9. No real Entra/Google exchange or workforce media generation has been run.

| Gate | Current result |
|---|---|
| Focused Python auth/configuration/Chirp tests at `e96f9899` | 372 passed; 11 existing DSPy deprecation warnings |
| Focused managed configuration tests at `e96f9899` | 216 passed with the external Prime producer case excluded |
| Unexcluded managed configuration tests | 216 passed, 1 failed: `Task7_original_producer_values_survive_managed_http_parser`, “Stage B requires the real producer fixture from its Python gate.” |
| Fresh Debug managed build | Passed; all existing target frameworks |
| Release rebuild / full managed suite | Pending Task 9 |
| Qualified packaged Python/MSAL payload | Pending Task 9 |
| Independent authentication/whole-branch review | Pending Task 9 |
| Installed firm sign-in and media acceptance | Not run; administrator setup, two approved identities and spend approval required |
| Private resource/user/quota billing attribution | Pending live observation |

No output parsing/allocation limits changed in this workforce implementation. The earlier inline-video memory measurements retain their original host/commit scope; they are not claimed as measurements of a new installed workforce pilot. Existing local-stop/publication and restart tests remain automated proof, distinct from the three-video live budget.

Actual settings, identifiers, caches, assertions, logs, account/project mappings and generated media remain outside all repositories/worktrees. Committed fixtures use synthetic identifiers. See the [administrator setup guide](../../guides/enterprise-google-workforce-setup.md).
