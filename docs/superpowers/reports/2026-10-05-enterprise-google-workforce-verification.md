# Workforce federation verification

Implementation uses the approved MSAL public desktop and Google auth STS assertion contract. Credentials remain Python-owned, with DPAPI-protected persistence; workforce media reuses the existing RookVision providers, managers, ledger and artifact pipeline.

Automated implementation evidence and installed live acceptance are separate gates. Tasks 1–8 and the independent review's four source fixes are implemented. Task 9 remains incomplete because the required packaged dependency audit failed under the approved pins. Task 10 has not started. No real Entra/Google exchange or workforce media generation has been run.

Final source tested: `c9540cd6b624555f6fd1ec6fb0d70652cbba5bfe`, branch `codex/enterprise-google-media`. This report update changes documentation only.

| Gate | Current result |
|---|---|
| Focused Python auth/configuration/Chirp tests at `e96f9899` | 372 passed; 11 existing DSPy deprecation warnings |
| Focused managed configuration tests at `e96f9899` | 216 passed with the external Prime producer case excluded |
| Unexcluded managed configuration tests | 216 passed, 1 failed: `Task7_original_producer_values_survive_managed_http_parser`, “Stage B requires the real producer fixture from its Python gate.” |
| Final Python Vertex/Chirp source suite | 395 passed; 11 existing DSPy deprecation warnings |
| Final managed configuration suite | 22 passed, including committed activation failure/cancellation display |
| Fresh Debug and Release managed Rebuild | Both passed; all configured targets, 0 errors |
| Final unexcluded whole managed suite | 4,253 passed, 2 prerequisite failures; detailed below |
| Final whole managed suite scoped to available prerequisites | 4,253 passed; excludes exactly the two documented absent prerequisites |
| Python runtime packaging / wheelhouse policy tests | Passed; final staged-payload check explicitly deferred because no successful release manifest was produced |
| Authority CPython runtime input | Official CPython 3.11.9 Windows x64 NuGet SHA-256 verified: `9283876d58c017e0e846f95b490da3bca0fc0a6ee1134b2870677cfb7eec3c67` |
| Packaged runtime build attempt | At clean `53dcd439`, both isolated offline Rook/Chirp installs, imports and `pip check` passed; required dependency audit failed before final manifest |
| Qualified final packaged Python/MSAL payload | Failed prerequisite; final source has not been packaged/deployed |
| Independent authentication/whole-branch review | Fresh independent review of `bc19d4af..53dcd439`: 137 focused Python tests passed; four Important findings, no Critical/Minor findings; all four fixed with failing-then-passing regressions and fresh source suites |
| Installed firm sign-in and media acceptance | Not run; administrator setup, two approved identities and spend approval required |
| Private resource/user/quota billing attribution | Pending live observation |

## Independent review fixes

- Committed activation failure and post-commit cancellation retain the newly active generation, cleared pending/legacy state and retirement block. A closed failed configuration response carries local status to C#; UI cancellation reconciles local status without retrying authorization or claiming success.
- Every deliberate disconnect persists an authorization-epoch tombstone, including an empty profile. A browser held in a different configuration-service instance cannot restore the first legacy authorization afterward.
- Initial metadata, browser and post-browser deadlines reach the asynchronous configuration caller. Expired workers remain retained and revoked until they settle, and cannot activate late. Entra `read1` and unaggregated STS reads yield between network chunks; real local slow-response tests exercise both transports without cloud traffic.
- Legacy save/disconnect release the credential mutex before Chirp recycling. Deterministic concurrent tests use the actual launch guard and replacement lock; neither test starts a child process.

The first broader Python run overlapped the heavy package build and failed one existing Windows child-process startup handshake before its mutex test could begin. The final plan suite passed twice without changing or weakening that test's timeout. The final managed unexcluded failures are `Task7_original_producer_values_survive_managed_http_parser` (missing real external Prime producer fixture: “Stage B requires the real producer fixture from its Python gate”) and `SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign` (absent historical `2026-06-13-rir-gh-solver-enabled-race-design.md`, also absent in the primary checkout). Their fixtures/documents were not fabricated, and the unexcluded gate is not described as passed.

## Packaged qualification blocker

The source-build authority used clean Rook `53dcd439`, clean Chirp `12230c7a9ce71104a4de31f9bc29b444cbc0b135`, accepted hash-locked dependency wheels and the exact MSAL 1.39.0 wheel (`2d2577886906cd7293850dffa2da29119966c213bfc6ec0cecf8bf7621e1ca77`). No broker extras were admitted. Both offline verifiers imported Rook/Chirp from isolated site-packages, confirmed MSAL 1.39.0 and Google auth 2.56.3, matched installed versions to the locks, removed installation caches before checks, and reported no broken requirements. These are partial runtime-input results for that build source, not qualification of the final source.

The audit reported LiteLLM 1.89.4 (`PYSEC-2026-4066`) and PyJWT 2.14.0 (`PYSEC-2026-4141`). No new vulnerability ignore was added, no release manifest was fabricated, and the attempted payload was not installed. The first invocation also exposed an operator error from a relative BuildRoot; the corrected absolute-path invocation reached the separate audit failure.

The [security-pin remediation proposal](../plans/2026-10-05-enterprise-google-workforce-runtime-pin-remediation.md) specifies LiteLLM 1.89.7 and PyJWT 2.15.0, verified universal-wheel hashes, a clean targeted advisory check and the required full graph/test/package gates. Accepted pins remain unchanged pending review and approval. A clean final-source authority rebuild is required afterward.

No output parsing/allocation limits changed in this workforce implementation. The earlier inline-video memory measurements retain their original host/commit scope; they are not claimed as measurements of a new installed workforce pilot. Existing local-stop/publication and restart tests remain automated proof, distinct from the three-video live budget.

Actual settings, identifiers, caches, assertions, logs, account/project mappings and generated media remain outside all repositories/worktrees. Committed fixtures use synthetic identifiers. See the [administrator setup guide](../../guides/enterprise-google-workforce-setup.md).
