# Configurable fal acceptance

This procedure separates deterministic qualification, installed runtime freeze, and later paid acceptance. No held-out endpoint is selected by the shipped synthetic fixtures. The production catalog remains empty. Fixture passes do not establish live acceptance.

## Candidate qualification

Work from the committed candidate checkout. Use the Python dependency environment with `PYTHONPATH` set to this checkout's `mcp_server/src`; verify `rook.__file__`. Set `ROOK_TEST_PYTHON` to that interpreter for required gateway captures. All builds suppress incidental installation with `-p:RhinoPluginDir=`.

```
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug -f net48 --filter "FullyQualifiedName~FalConfiguredConformance|FullyQualifiedName~FalQualificationHarness" -p:RhinoPluginDir=
powershell -NoProfile -File scripts/tests/verify-fal-config-acceptance.tests.ps1
Rook.Vision.Qualification.exe verify-cases --catalog CATALOG --cases CASES.json --report REPORT.json
```

The qualifier is built from `src/Rook.Vision.Qualification` for net48/net7.0/net8.0. Run the existing `scripts/verify-vision-merge.ps1 -Python <dependency-python>` once after committing the candidate. Its three full Release managed runs are mandatory. It records the interpreter/import origin, Node controls/panel tests, Python contracts, both qualification-host builds, catalog validation, acceptance-checker tests, and existing stress/FFmpeg checks.

Build native Release from a fresh VS2022 shell with `vcvarsall.bat x64 -vcvars_ver=14.44`, then MSBuild with `/p:VCToolsVersion=14.44.35207`. Build RookBim after the companion. Run the four default Task10 script suites after all Release payloads exist: `deploy-vision-model-catalog.tests.ps1`, `deploy-local-testing-guards.tests.ps1`, `release-installer-guards.tests.ps1`, and `validate-release-artifacts.tests.ps1`. No reduced package switches qualify this gate.

## Generic case data and transport evidence

`verify-cases --catalog ROOT --cases JSON --report JSON` is offline. Every request reaches the production configured parser/normalizer, real quote validation, bounded media preparation, and `FalConfiguredExecutor`/`FalApiClient`. An ordered `HttpMessageHandler` fixture is the only HTTP transport; unexpected calls or mismatched methods, URLs, JSON, media digest, or unconsumed fixtures fail. No fixture input can supply executable code, callbacks, a live credential or an alternate transport.

Case document schema:

- `schema_version: 1`, nonempty `cases` array, optional `required_regressions` traceability rows for existing lifecycle/handler/compiler suites run by the full regression gate.
- Each case: unique descriptive `id`; `surface: panel|mcp|managed`; `request` using the public managed model/operation/common/options/artifact-media contract.
- `panel_values`: qualified field names such as `request.seed` or `options.strength`, mapped to raw strings. `panel_config` forwards existing operation/media/artifacts configuration to the actual Node capture. Defaults are omitted. `panel` calls the real rendered controls and confirmation handlers twice, first to obtain the exact managed quote and then to submit that quote. `mcp` runs the production `rook_tools_call` gateway exporter for estimate and confirmed submit. Neither surface is reconstructed from source strings.
- `media_bytes`: offline fixture objects `{artifact_id,artifact_role,mime,base64}` matching request references. Bytes pass real snapshot capture/preparation. They never enter reports. Upload fixtures can assert `request_bytes_sha256` against the PUT body.
- `protocol`: ordered `{method,url,status,body}` responses, optionally `raw_body`, `request_json`, `request_bytes_sha256`, or `exception: network|timeout`. These URLs are inert fixture expectations; there is no network handler.
- `actions`: ordered `status`, `result`, `cancel`, `restore_cancel`, or `unsupported_snapshot` calls. Restore cleanup uses only the serialized pinned authority, with no catalog lookup. Unsupported snapshots must not permit cleanup.
- `observer`: optional fixed fault injection `before_upload`, `before_dispatch`, or `accepted_write`. `confirmation` can supply invalid confirmation data. `quote_changes` supplies a different otherwise-valid quoted request to exercise stale-input rejection.
- `expected`: required `outcome` and exact `calls`; optional exact `provider_payload`, `field`, `disposition`, `result_role`, `result_mime`, `result_count`, `status_outcome`, `cancel_outcome`, `cleanup_available`, effective controls and dispatch events. Assertions compare canonical JSON including numeric values, never only a success boolean.

Reports include case identity, endpoint/operation, descriptor and definition hashes, exact effective controls, quote/cap, normalized request/media digest, actual fake-client provider payload/digest, semantic media role/order/content digests, lifecycle outcomes and sanitized saved provenance. HTTP credentials are never recorded. Transport URLs/data URIs become `{redacted_sha256:...}`. Scalar provider controls remain exact. Fixture artifact roles at the provider boundary are `image`/`video`; publication roles are covered by existing manager suites.

`estimate_request_sha256` identifies the actual captured estimate request. `request_sha256` identifies the final captured **confirmed submission**, including its `quote_fingerprint` and `max_estimated_cost_usd`. Both use `FalCanonicalJson.Hash`: ordinal object-key ordering, preserved array order, and exact normalized numeric lexemes. The acceptance capture must use this same final-submit digest; the no-cost utility's diagnostic argument hashes are not a substitute. Each successful row also records `quote:{quote_fingerprint,max_estimated_cost_usd,pricing}` and `confirmation:{quote_fingerprint,max_estimated_cost_usd}`. `cap_usd` is the confirmed cap, which may exceed the quoted upper bound. Public pricing retains its existing exact decimal-text projection where required.

The fixtures cover synchronous/queued image and queued video, nondefault and omitted common/provider controls through both real surfaces, safe-large seed, six-place precision, raw lossy panel rejection, ordered artifact media, malformed options/types/bounds/conditions, stale audio quote, provider uncertainty, admission/persistence failures, result cardinality/MIME, pinned cleanup and unsupported snapshot. The case document also maps all five review focuses and all three user findings to the existing full regression suites. Those suites provide the manager stop-fence races, media/pricing revision races, filesystem junction/collision rejection and both formerly-configured image-entry rejection checks.

## Installed no-cost checkpoint

Prepare Release payloads and sealed candidate-specific Python inputs before touching installed state. The authoritative local workflow is `scripts/deploy-local-testing.ps1`; release mode requires explicit `-PythonBuildRoot` and verified `-PrimeRuntimePayload`, matching candidate wheel source commit and absent `PYTHONPATH`. A missing sealed input is not authorization to choose a dev runtime. Preserve Rhino and Grasshopper work and close them normally before deploy/copy. A saved GH path alone does not establish that its document is unmodified.

After the controller's installation checkpoint, deploy the candidate and restart Rhino. Use installed MCP, never direct HTTP, for discovery/error smoke. If the running connector is stale, the frozen generic utility is:

```
python scripts/verification/capture-fal-installed-mcp.py --python INSTALLED_PYTHON --requests REQUESTS.json --report REPORT.json
```

Requests are `{calls:[{name,arguments}]}`. The utility launches the supplied installed interpreter with `-I -m rook`, clears PYTHONPATH, checks the package origin is under that interpreter's site-packages, records executable hash and actual MCP inventory, and invokes the real gateway. Only no-cost discovery, quote and job-read names are admitted; generation/cancellation/mutation requests fail locally. Saved responses redact transport media and credentials. Inspect `is_error` and returned envelopes against intended positive/negative expectations; process exit alone is not a smoke assertion. Initial empty-catalog requests include `rhino_ping`, `rhino_image_models`, `rhino_video_models`, unknown-model image/video estimates and invalid job reads. Run native route/callback admission probes through MCP as well.

For the installed configured-panel smoke, copy ONLY `catalog.json` and the definition files it lists from the synthetic fixture directory into a separate attempt catalog, then use `deploy-vision-model-catalog.ps1 -CatalogRoot <attempt-catalog> -PluginRoot <installed> -ValidatorPath <Release-qualifier>` with Rhino closed. Restart Rhino; discover synthetic models in UI/MCP, inspect common/provider/media controls, enter nondefault/omitted/precision values and obtain quotes. Never confirm generation. Capture diagnostics/validation with no provider calls. Close normally, restore the empty source catalog using the same copier, restart, and prove synthetic model absence before final freeze. Preserve copier receipts and verify code hashes remain unchanged across both copies.

Collect actual loaded native and companion paths using `(Get-Process -Id <verified-rhino-pid>).Modules`, selecting `RookNative.rhp` and `Rook.rhp`. Record module FileName, FileVersionInfo, SHA256, process ID/start time and observation UTC. Record installed Python executable and `rook.__file__` from the isolated subprocess. Do not infer loaded identity from build output or disk existence.

## Freeze

After every deterministic, native, target, package and installed gate passes:

```
Rook.Vision.Qualification.exe freeze-runtime --repo CHECKOUT --plugin-root INSTALLED_PLUGIN --mcp-root INSTALLED_ROOK_ROOT --out artifacts/fal-config-acceptance/ATTEMPT/freeze.json
```

The manifest enumerates source/harness roots, Release artifacts for every managed target and qualifier, native Release artifacts, and installed plugin/MCP trees (including packaged dependencies and embedded UI bytes). Each file has relative path, byte count and SHA256. Comparison detects additions/deletions as well as changed bytes. Roots, source and built payloads reject reparse paths. JSON configuration is excluded only at exact source/installed catalog locations, never the Models code directory. Source generated bin/obj/venv/node_modules and installer staging runtime/artifacts are excluded; authoritative Release/installed payloads are separately inventoried. Installed mutable data exclusions apply to known data/log extensions below root logs/artifacts/data/cache; code there remains frozen. Exact `.env`, `secrets.json` and generated `__pycache__` directories are excluded. Standalone `.pyc` files remain inventoried because Python can execute them without source files. Store evidence outside frozen trees. Loaded-runtime evidence is separate and mandatory.

Installed roots may contain Windows directory junctions with a single absolute target that is a direct physical directory inside the same root. This accommodates UV's Python version alias without omitting executable runtime bytes. The freeze reads metadata with a fixed hidden, noninteractive PowerShell command (10-second timeout, 16-KiB output limit per stream); paths are passed through a child environment variable, never command interpolation. It records `{path,kind:"directory_alias",link_type:"Junction",target,sha256,bytes}`, where `target` is root-relative and the digest/byte count cover UTF-8 `Junction\n<target>`. The physical target's files are inventoried normally. Alias identity and target bytes both participate in comparison. External, relative, unresolved, multiple, excluded, chained, ancestor and cyclic targets reject; aliases themselves are never traversed. Catalog compilation and the Task10 copier retain their strict reparse rejection.

Installed catalog paths are `net48/vision-models/fal`, `net7.0/vision-models/fal`, and `net8.0/vision-models/fal` directly under the plugin root, matching the Task10 copier. Only JSON files are allowed to change. A directory with a data extension is still traversed, so `data/run.log/adapter.py` and `net8.0/vision-models/fal/model.json/adapter.dll` remain frozen.

Additional installed mutable file exclusions follow existing writer contracts:

| Exact relative path or filename shape | Writer |
| --- | --- |
| `discovery/instance-<digits>-native.json[.tmp]`, `companion-<digits>.json[.tmp]`, `companion-load-<digits>.log`, `native-discovery-<digits>.log` | `RookServer.cpp`, `RookNativePlugin.cpp`, `CompanionRuntimeStatus.cs` |
| `registry/owned_sessions.db`, `artifacts.db`, `work_units.db`, including their `-wal`, `-shm`, `-journal` companions | `registry.py`, `artifacts.py`, `work_units.py` |
| `data/rookchat/acp/v1/conversations/<32 lowercase hex>.json`, `presentation/<32 lowercase hex>/<8 digits>.json`, `claims/<64 lowercase hex>.open.claim` | `runtime_paths.py`, `acp_storage.py`, `acp_presentation.py` |
| `data/context_history.json`, `metrics.json`, `agent_metrics.json` | `context_storage.py`, `metrics_store.py`, `base_agent.py` |
| `data/dspy-cache/[<3 digits>/]cache.db` and `app/chirp/data/dspy-cache/[<3 digits>/]cache.db`, including SQLite sidecars above | `learning/dspy_config.py`, `chirp_manager.py` |

These are file exclusions, not directory exclusions. Unknown JSON/SQLite files, `data/model_profiles.json`, runtime code under `prime-uv`, and legacy `chat` directories remain frozen. There is no general JSON exclusion for MCP data and no exclusion for pickle files.

No held-out endpoint definition or endpoint-specific test exists in the initial freeze. Record reviewer sign-off after freeze, then select new endpoints. Any source/runtime/harness change invalidates that attempt and requires a new committed candidate, affected qualification, freeze and new held-out endpoints.

## Later paid acceptance evidence

Select one compatible image and video endpoint after freeze. Record official schema/pricing review and at least two useful provider controls per endpoint beyond common selectors, including numeric and boolean/enum across the pair. Obtain the maintainer's concrete total spend cap before four live jobs, one per endpoint/surface. Add only catalog definition JSON. Capture each real UI/MCP submitted request and replay its inputs as data through the frozen generic fixture harness to prove exact provider-boundary fields. Live content is not evidence that a control was transmitted. The boundary payload digest identifies that instrumented fixture proof, not a claim that raw private live transport was logged.

Acceptance command:

```
powershell -NoProfile -File scripts/verify-fal-config-acceptance.ps1 -FreezeManifest freeze.json -Cases held-out-cases.json -Evidence evidence.json -Report acceptance.json
```

Evidence schema (version 1):

- `freeze_sha256`, `cases_sha256`; `reviewer`, `reviewed_utc`; `spend_authorization:{maintainer,approved_utc,cap_usd}`.
- `endpoints`: exactly two records `{model_id,endpoint,operation,modality,definition_hash,selected_utc,documentation:{url,reviewed_on,schema_sha256,pricing_sha256},controls:[{name,type}]}`. Official URLs use fal.ai/docs.fal.ai; record exact reviewed document digests.
- `live_jobs`: exactly four distinct `{case_id,job_id,artifact_id,model_id,endpoint,operation,definition_hash,runtime_sha256,surface,mode:"live",state:"completed",result_mime,request_sha256,normalized_sha256,payload_sha256,quote_fingerprint,max_estimated_cost_usd,started_utc,completed_utc,selected_controls,actual_spend:{status:"reported"|"unavailable",usd?},capture,provenance,artifact}`. Runtime hash is the freeze file hash. Never infer actual spending from estimated caps.
- All file links are `{path,sha256}` relative to the evidence directory. `capture` records `surface`, final-submit/normalized/boundary payload digests, the actual `confirmation:{quote_fingerprint,max_estimated_cost_usd}`, and `quote:{quote_fingerprint,max_estimated_cost_usd,pricing}` from the confirmed estimate. `provenance` records matching job/artifact/definition identity plus saved `effective_request`, `effective_options`, `pricing`, and ordered `media` from the persisted configured-fal snapshot. These values must match the conformance row; declared selected controls must retain their numeric/boolean/string types and match its effective options. `artifact` hashes the downloaded result.
- `conformance` links the successful frozen qualifier report for the exact case file. Jobs join its case IDs, final submitted-request digest, normalized/media hashes, payload/definition hashes, quote fingerprint and confirmed cap. The captured quote's pricing must match saved provenance, and the confirmed cap must cover the quoted bound.
- `qualification`: named `{name,exit_code:0,path,sha256}` evidence for `native_build`, `managed_builds`, `regression`, `package`, `installed_mcp`, `installed_panel`, `loaded_paths`. Logs/reports retain full commands and real exit codes. `loaded_paths` JSON contains `{process_id,process_started_utc,observed_utc,modules:[{name,path,version,sha256}],python:{path,package_path,sha256,package_sha256}}`. Module/executable/package files must match exact frozen inventory records. `python.path` is the deployed `<mcp_root>/venv/Scripts/python.exe`; `package_path` is the actual existing `rook.__file__` under that environment's private `Lib/site-packages/rook` directory, not an inferred package directory. Record its SHA256 as `package_sha256`.

Required chronology is `freeze.created_utc ≤ reviewed_utc < selected_utc ≤ started_utc ≤ completed_utc` for every job, with maintainer spend approval no later than each paid start. Selection before sign-off and jobs before endpoint selection fail independently.

The checker verifies the frozen qualifier and every dependency before executing it, regenerates inventories, checks exact file sets/hashes, allows only configuration JSON and acceptance prose Git changes, validates evidence links and joins, checks all four live jobs and spend-cap sum, and requires installed evidence. Missing live/installed proof returns nonzero `incomplete_or_failed`; fixture success cannot replace it. Local evidence is an auditable record, not a cryptographic attestation of remote billing.
