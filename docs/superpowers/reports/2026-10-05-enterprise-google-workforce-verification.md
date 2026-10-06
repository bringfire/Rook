# Workforce federation verification

Implementation uses the approved MSAL public desktop and Google auth STS assertion contract. Credentials remain Python-owned, with DPAPI-protected persistence; workforce media reuses the existing RookVision providers, managers, ledger and artifact pipeline.

Automated implementation evidence and installed live acceptance are separate gates. Tasks 1–9 are complete, including the independent review's four source fixes and final packaged qualification. Task 10 has not started. No real Entra/Google exchange or workforce media generation has been run, and the qualified payload has not been deployed into installed Rook.

Final production source tested and packaged: `2c993d3a942cc071f92f4538594d210ca1cccb8f`, branch `codex/enterprise-google-media`. Matching clean Chirp source: `12230c7a9ce71104a4de31f9bc29b444cbc0b135`. This evidence commit adds documentation and the reproducible packaged smoke fixture; it changes no packaged product bytes.

| Gate | Current result |
|---|---|
| Focused Python auth/configuration/Chirp tests at `e96f9899` | 372 passed; 11 existing DSPy deprecation warnings |
| Focused managed configuration tests at `e96f9899` | 216 passed with the external Prime producer case excluded |
| Unexcluded managed configuration tests | 216 passed, 1 failed: `Task7_original_producer_values_survive_managed_http_parser`, “Stage B requires the real producer fixture from its Python gate.” |
| Final expanded Python auth/Vertex/Chirp/text/DSPy/configuration suite | 550 passed, 5 deselected; 11 existing DSPy deprecation warnings; exact missing external prerequisites below |
| Final managed configuration suite | 22 passed, including committed activation failure/cancellation display |
| Fresh Debug and Release managed Rebuild | Both passed; all configured targets, 0 errors |
| Final unexcluded whole managed suite | 4,253 passed, 2 prerequisite failures; detailed below |
| Final whole managed suite scoped to available prerequisites | 4,253 passed; excludes exactly the two documented absent prerequisites |
| Python runtime packaging / wheelhouse policy tests | Both passed against the actual final staged payload; release validator passed 1.6.1 with 109 wheels |
| Authority CPython runtime input | Official CPython 3.11.9 Windows x64 NuGet SHA-256 verified: `9283876d58c017e0e846f95b490da3bca0fc0a6ee1134b2870677cfb7eec3c67` |
| Historical packaged runtime build attempt | At clean `53dcd439`, offline verification passed, but required dependency audit failed; replaced by the qualified final-source build below |
| Qualified final packaged Python/MSAL payload | Passed at clean `2c993d3a`: both isolated offline installs/imports, exact lock matching, `pip check`, cache removal and dependency audits; no broker extras |
| Packaged auth smoke on CPython 3.11.9 | Passed: actual MSAL with synthetic signed ID tokens, actual Google SDK STS wire, forced refresh, missing-oid refusal/cache preservation and Windows DPAPI/disconnect tombstone; zero cloud traffic |
| Independent authentication/whole-branch review | Fresh independent review of `bc19d4af..53dcd439`: 137 focused Python tests passed; four Important findings, no Critical/Minor findings; all four fixed with failing-then-passing regressions and fresh source suites |
| Installed firm sign-in and media acceptance | Not run; administrator setup, two approved identities and spend approval required |
| Private resource/user/quota billing attribution | Pending live observation |

## Independent review fixes

- Committed activation failure and post-commit cancellation retain the newly active generation, cleared pending/legacy state and retirement block. A closed failed configuration response carries local status to C#; UI cancellation reconciles local status without retrying authorization or claiming success.
- Every deliberate disconnect persists an authorization-epoch tombstone, including an empty profile. A browser held in a different configuration-service instance cannot restore the first legacy authorization afterward.
- Initial metadata, browser and post-browser deadlines reach the asynchronous configuration caller. Expired workers remain retained and revoked until they settle, and cannot activate late. Entra `read1` and unaggregated STS reads yield between network chunks; real local slow-response tests exercise both transports without cloud traffic.
- Legacy save/disconnect release the credential mutex before Chirp recycling. Deterministic concurrent tests use the actual launch guard and replacement lock; neither test starts a child process.

The first broader Python run overlapped the heavy package build and failed one existing Windows child-process startup handshake before its mutex test could begin. The final plan suite passed twice without changing or weakening that test's timeout. The final managed unexcluded failures are `Task7_original_producer_values_survive_managed_http_parser` (missing real external Prime producer fixture: “Stage B requires the real producer fixture from its Python gate”) and `SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign` (absent historical `2026-06-13-rir-gh-solver-enabled-race-design.md`, also absent in the primary checkout). Their fixtures/documents were not fabricated, and the unexcluded gate is not described as passed.

## Packaged qualification and resolved audit failure

The source-build authority used clean Rook `53dcd439`, clean Chirp `12230c7a9ce71104a4de31f9bc29b444cbc0b135`, accepted hash-locked dependency wheels and the exact MSAL 1.39.0 wheel (`2d2577886906cd7293850dffa2da29119966c213bfc6ec0cecf8bf7621e1ca77`). No broker extras were admitted. Both offline verifiers imported Rook/Chirp from isolated site-packages, confirmed MSAL 1.39.0 and Google auth 2.56.3, matched installed versions to the locks, removed installation caches before checks, and reported no broken requirements. These are partial runtime-input results for that build source, not qualification of the final source.

The audit reported LiteLLM 1.89.4 (`PYSEC-2026-4066`) and PyJWT 2.14.0 (`PYSEC-2026-4141`). No new vulnerability ignore was added, no release manifest was fabricated, and the attempted payload was not installed. The first invocation also exposed an operator error from a relative BuildRoot; the corrected absolute-path invocation reached the separate audit failure.

The [security-pin maintenance plan](../plans/2026-10-05-enterprise-google-workforce-runtime-pin-remediation.md) records deliberate Task 9 maintenance to LiteLLM 1.89.7 and PyJWT 2.15.0. Maintainer advisories, universal-wheel hashes, a clean targeted audit and the exact two-package resolver diff were reviewed before admission. All other versions and extras remain unchanged. A hash-verified test overlay exercises updated libraries without changing the shared development environment or installed Rook. The subsequent clean final-source authority rebuild at `2c993d3a` passed both isolated runtime verifiers and both dependency audits. The audits retain only the pre-existing cache exception `CVE-2025-69872`; this work added no ignore.

Expanded text/DSPy/configuration/auth regression testing under these updated pins found five additional cases requiring the same absent real Prime checkout/Node loader: `test_task7_real_prime_writer_sdk_http_and_panel_fixture` and the four parameterizations of `test_real_prime_writes_refresh_and_replacement_preserve_acl`. The unexcluded expanded run passed 550 cases and failed those five prerequisite cases. The scoped rerun excludes exactly these two functions, with all available tests retained. They are not treated as a successful real Prime integration gate.

Final verification rebuilt Debug and Release before the managed tests, with zero build errors, then passed the scoped 550 Python and 4,253 managed tests and both packaging-policy suites. An operator-only Bash/PowerShell module-path issue and propagation of an intentionally failing negative test's exit code were corrected in the ignored verification runner. Product validators and negative tests were not weakened.

The authority build uses release version 1.6.1 and the verified CPython 3.11.9 input above. Qualified runtime pins include MSAL 1.39.0, Google auth 2.56.3, PyJWT 2.15.0, LiteLLM 1.89.7, Requests 2.34.2 and packaged Cryptography 50.0.1. The existing development Cryptography profile remains 50.0.0. The [packaged smoke fixture](../../../mcp_server/tests/fixtures/vertex_workforce_packaged_smoke.py) runs with the isolated installed-wheel interpreter and `-I`; it verifies module origins and production-source equality as well as the synthetic SDK/DPAPI lifecycle. It does not substitute for live identity, policy, model or billing checks.

| Qualified artifact | SHA-256 |
|---|---|
| Runtime manifest | `3f83936871cce252d91dfab2c343908affb14fde73f37f72778b47b89e5cdfc0` |
| Rook 1.6.1 wheel | `1c69c4182ca53bd9d8cbb692096ca505badede1acfb792adff0eaf54ac2d7a41` |
| Chirp 0.1.0 wheel | `2a1203c382424c09412804c3f65af5819ee3a690cbb945861a66764d0786ebce` |
| Rook dependency audit JSON | `d9c58b53ad115c5cb97e0b4165d2dd74126a54ee16b9942c1743f4865efe8064` |
| Chirp dependency audit JSON | `bee0c342eb8ab8c3a0196ecde4a77340a8de3faf5008b0b1b97e94ef58e9eb0c` |

The full manifest, raw build logs and local staging paths remain uncommitted. Installed acceptance still requires private Entra/workforce-pool/project setup, two permitted identities and explicit approval of the one-image/three-video budget. No cloud application, IAM grant or Conditional Access change was made by this implementation.

No output parsing/allocation limits changed in this workforce implementation. The earlier inline-video memory measurements retain their original host/commit scope; they are not claimed as measurements of a new installed workforce pilot. Existing local-stop/publication and restart tests remain automated proof, distinct from the three-video live budget.

Actual settings, identifiers, caches, assertions, logs, account/project mappings and generated media remain outside all repositories/worktrees. Committed fixtures use synthetic identifiers. See the [administrator setup guide](../../guides/enterprise-google-workforce-setup.md).
