# RookChat Runtime Adoption Source Preparation

**Status:** Source preparation only, for independent review. No acquisition, real build, assembly, installation, authentication or working-installation switch is authorized by this note. A neighboring verifier test remains failed as recorded below; this is not an all-green execution package.

## Source identities and changes

- Accepted Rook Task 7 baseline: `00aedab0b54832d8d21d888d5658a89199952b5f`.
- Separate UTC correction commit: `2b2299c28b2c175c079a3737c4e84607c4813bbd`, directly over that baseline. Only `scripts/build-prime-acp-runtime.sh` and its existing Bash test suite changed. The script sets `TZ=UTC0`; the non-UTC test verifies both emitted Z timestamps fall inside the actual invocation interval.
- Prime remains at reviewed `c2055d6aff5891b918a24accf584a76852676445`, parent `2cba570236a80a5230a37d930a64bd2c532d1a4b`, ref `refs/heads/codex/rookchat-configuration`. No Prime changes.
- The commit containing this note updates `prime_runtime_artifact.PRIME_COMMIT` and `prime_runtime.SUPPORTED_CONFIGURATION_COMMITS` together to that exact Prime commit. The supported set contains that one identity only. These source values do not activate the feature in the installed product.
- Existing tests cover new manifest provenance, production support selection, historical compatibility and directory binding. The old independent manifest byte/hash oracle remains frozen to its historical identity; it was not rewritten to mimic new serializer output.
- No actual new runtime ID exists yet. Synthetic fixture manifest IDs are not adoptable artifacts.

## Historical compatibility and account transition

The real catalog selects the current pointer for new conversations and the recorded exact runtime ID for historical conversations. Tests exercise both verified synthetic payloads and the production launch factory for create/reopen. Historical configuration remains unavailable; historical argv has no new policy flag. Missing historical payloads refuse rather than select the new runtime. Reopen does not gain model/reasoning overrides, a changed cwd or a substituted session path.

Supported-runtime configuration and ACP launches use the same service-owned `data_root/prime-config` and `--configuration-policy rookchat`. Historical launches retain their previous base-environment binding. Tests supply a distinct, nonsecret historical `PRIME_AGENT_CODING_AGENT_DIR` and prove new launch preparation does not mutate it or redirect historical launches.

**Execution-package requirement:** before switching the installation, record the actual historical nonsecret directory binding and how it reaches the service/Prime child, then preserve it explicitly through the selected deployment workflow. If the old path was implicit, establish its nonsecret resolution rather than assuming the new directory is interchangeable. Do not globally replace the historical binding with `prime-config`, copy credentials, edit associations, delete claims or migrate old conversations. If the existing deployment workflow cannot preserve that binding, stop for review rather than patching around it during execution.

Fresh connection through RookChat is a recommendation, not a decision made here. The user may approve that later or defer switching the installation. No current credential/account contents or access were inspected. Real directory protection and synthetic writer-to-consumer validation must precede any separately authorized credential write. New authentication does not silently redirect historical conversations.

## Local verification

| Gate | Result |
| --- | --- |
| UTC regression RED | 36 passed, 1 failed; exit 1. Under `TZ=EST5`, the timestamp was five hours behind the observed UTC interval. |
| Existing Bash suite GREEN | 37 passed; exit 0. Both timestamps checked; builder/tools are synthetic. |
| Adoption causal RED | 4 failed; exit 1, on old pin/empty-set assertions. |
| Adoption causal GREEN | 4 passed; exit 0. |
| Expanded Python neighbors | 265 passed, 1 failed; exit 1, 63.17 seconds. Not a passing aggregate gate. |

Python breakdown: runtime 51/51; manifest artifact 64/64; configuration 74/74; package assembly 37/37; post-install 3/3; installed verifier 36/37. All are temporary/synthetic fixtures, not real packaging, installation or authentication qualification. The configuration fixture includes the previously approved model-free source producer; it does not call a model. No managed gate was rerun; the existing separate-host limitation remains.

**Remaining verification issue:** `test_clean_crlf_checkout_compares_exact_installed_bytes[False]` refuses with `verifier implementation differs from reviewed source`. Read-only inspection of its exact retained fixture found that the executing verifier and fixture checkout share raw blob `2227025bdf24273a4a7f9bdb61c8df489fe3b781` (171 CRLF lines), while the fixture's committed LF blob is `1c1787a26f76a8eb56081d8b8c9db770cff74766`. `matches_blob()` compares raw bytes using `--no-filters` and therefore refuses at verifier authenticity, before the installed-byte checks.

That verifier's tracked blob is also `1c1787a26f76a8eb56081d8b8c9db770cff74766` at both the accepted Task 7 baseline and this UTC parent. Neither its implementation nor its tests were edited. This establishes the failing comparison, not a passing test or complete baseline execution comparison. No normalization, authenticity waiver or out-of-scope verifier repair was performed. Review this issue before approving an execution package that consumes the verifier.

Failure fixture: `C:/Users/bring/AppData/Local/Temp/pytest-of-bring/pytest-4774/test_clean_crlf_checkout_compa0/source`. It is disposable test output, not qualification evidence or installed data.

## Retained evidence and commands

Local ignored records under `C:/UDEV/Rook/.worktrees/rookchat-configuration/artifacts/rookchat-configuration/`; they are not available from a repository clone alone. All earlier evidence and historical build records remain unchanged.

| Record | SHA-256 |
| --- | --- |
| `task8-utc-red.log` | `6F8508F352A3A1C0F3C69E9526BCAF64FFDC3097154C622B4E78722A6A305F57` |
| `task8-utc-green.log` | `D5A56F7563998AFD327346A67B63D77B56A3FC09CD9EE5F365DF2A6F009FB48F` |
| `task8-adoption-red.xml` | `B9DA40480FC97C47022DBDD3A9243CDE71F5A376FFE807EBC8C28B10261AF3EE` |
| `task8-adoption-green.xml` | `D400CBE5567B84D66F598DAB14BCDDBF4905E0300368324AC2E0B55250590DD7` |
| `task8-adoption-neighbors.xml` | `8CA55837CE5461DA617FAAC668810C2B7A66B2CF8B64B7127CBF6E7FD0283025` |
| `task8-adoption-neighbors.log` | `3B9351B88DEB48CF8EA33368F7E7A2A9FC72D07F4E1BBEF6F5D04B5116ECEAEF` |

Bash: existing `scripts/tests/prime-wsl-build.tests.sh` was executed under `wsl.exe -d Ubuntu-24.04 --exec bash -lc`, with a 120-second outer timeout and five-second kill allowance. The two scripts were copied with CRLF removed into a fresh `/tmp/rook-utc-suite.XXXXXXXX` directory; no repository normalization occurred. The suite creates only synthetic repos/builders and removes its exact temporary roots. The real upstream builder was never invoked. The command and copy procedure are retained in `artifacts/rookchat-configuration/task8-source-preparation-commands.md`.

Python cwd: `C:/UDEV/Rook/.worktrees/rookchat-configuration/mcp_server`. Interpreter: `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe`; `PYTHONPATH` points only to the isolated worktree's `mcp_server/src`, and `PYTHONDONTWRITEBYTECODE=1`. Causal selection: `tests/test_chat_prime_runtime.py tests/test_prime_runtime_artifact.py tests/test_chat_configuration.py -k 'adoption_keeps or supports_only_reviewed_adoption or manifest_roundtrip_public_cli' -q --tb=short` with corresponding JUnit/output paths above. Expanded selection adds `tests/test_package_prime_acp_runtime.py tests/test_post_install_prime_runtime.py tests/test_verify_installed_rookchat_acp.py`, without the `-k` filter. Every enclosing command propagated the captured test exit code.

## Later gates, still held

1. Resolve the recorded verifier gate for review; freeze the final source/operator identities, tools, fresh roots and exact commands before execution.
2. Separately authorize named-ref bundle/WSL real build, then ZIP transfer, existing safe assembly and complete manifest verification. Preserve historical generations and stop on failure.
3. Separately authorize matched Rook release-component build/deployment, with explicit Chirp source, verified pip bootstrap, fresh wheelhouse/audits and matching `-PythonBuildRoot`/`-PrimeRuntimePayload`. Retain both blocker checks, exact source/installed byte checks, old runtime/configuration preservation and nonzero outer exit.
4. Separately authorize user-selected authentication and bounded live first-use checks. Release-mode components alone do not qualify the customer installer, onboarding, model access, D/E or customer-release security readiness.

The working installation, Prime checkout and unresolved unstaged knowledge modification are preserved. No developer account choice, live configuration change or installed pointer change was made.
