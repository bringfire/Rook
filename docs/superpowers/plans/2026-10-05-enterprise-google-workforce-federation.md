# Enterprise Google Workforce Federation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution method:** Native execution: the primary agent implements sequentially using `superpowers:executing-plans`. Preserve the user's selected method. Obtain an independent authentication/whole-branch review before installed live acceptance.

**Goal:** Let employees generate Google images and videos using the firm's Entra identity, with direct firm project billing and protected local credentials.

**Architecture:** MSAL owns Entra public-client protocol operations; Python owns the DPAPI-protected session, verified principal and STS exchange. Extend the existing Vertex store, internal token/configuration routes and managed lease contracts. Reuse existing RookVision providers, managers, ledger and artifact publication.

**Tech Stack:** Windows, Python >=3.10, packaged Python 3.11.9; `msal==1.39.0`, `google-auth==2.56.3`, existing PyJWT/cryptography/HTTP transports; existing C# net48/net7/net8 companion and tests.

**Spec:** `docs/superpowers/specs/2026-10-05-enterprise-google-workforce-federation-design.md` (revised after reviews of `50c8c4bd` and `33f975ba`).

**Status:** Written for review at the user's request. No implementation tasks below have run. MSAL's scoped dependency exception is approved; the selected STS contract, revised scope and this plan still require review before implementation. Cloud OAuth Preview is unapproved. Live credentials, configuration and spend are separate prerequisites.

## Global Constraints

- Use `POST https://sts.googleapis.com/v1/token`; external Entra ID token, token-exchange grant, access-token result, `cloud-platform` scope, canonical workforce audience and explicit `userProject` option. No client authentication or endpoint fallback.
- Required effective Entra scopes: exactly `openid profile offline_access`. MSAL reserves/adds these: resource scopes `[]`, no `exclude_scopes`, no Graph scopes.
- Python retains credential ownership and DPAPI persistence. No MSAL broker extras, MSAL Extensions, `pymsalruntime`, shared service-account keys or employee CLI requirement.
- Preserve development pins `requests==2.34.2`, `PyJWT==2.13.0`, `cryptography==50.0.0`; packaged pins `requests==2.34.2`, `PyJWT==2.14.0`, `cryptography==50.0.1`. Add only reviewed MSAL requirements; do not incidentally synchronize existing profiles.
- Task 9 audit correction: deliberate, reviewed security maintenance changes existing LiteLLM to 1.89.7 and PyJWT to 2.15.0 in both profiles. Review the exact two-package resolver/hash diff before admission, preserve all other pins/extras, and require the full package gate; see the linked spec and runtime maintenance evidence.
- Imports are pending, never active. Activation requires validated Entra identity plus successful STS exchange and atomic revision/authorization-epoch checks. Disconnect invalidates both slots and late candidates.
- Activation includes text/Chirp refusal and stop-only retirement in Task 4. Persist pending retirement until confirmed; failure keeps committed authorization, reports restart required and blocks workforce leases.
- Refresh writes require generation, verified principal and expected cache revision, plus cancellation/deadline checks under the mutation lock. Set the thread-safe cancellation event before releasing the async lock on timeout.
- One active Google authorization per Windows user; opaque version-2 firm binding; same-principal refresh stable, successful reconnect rotates. Zero fallback to ambient credentials.
- First workforce slice: images/videos. Vertex text and Vertex-required Chirp under workforce mode fail explicitly before dispatch/startup; preserve all legacy and non-Vertex behavior.
- Imports <=64 KiB, serialized MSAL cache <=256 KiB, version-2 store <=512 KiB, assertion/token/JWKS responses <=1 MiB, claim clock tolerance <=60 seconds.
- Token issuance <=30 seconds aggregate, individual request <=20 seconds. Browser interaction <=180 seconds; fixed owned configuration request ceiling 210 seconds.
- Firm **Check sign-in** tests identity/exchange only: no model requests; image/video access, billing and quota remain explicitly unverified.
- Existing image model `vertex_ai/gemini-3.1-flash-image` at `global`; video `vertex_ai/veo-3.1-fast-generate-001` at `us-central1`. Shared region changes require deliberate active save.
- One submission dispatch per job; no automatic resubmit; restart interrupts without automatic poll/fetch. Local stop is not confirmed remote cancellation.
- Actual account/tenant/project/client/pool values, credentials, private evidence and media stay outside repository/worktrees. Examples and tests are synthetic.
- No C++/Revit/public MCP/Prime protocol changes. Each task commit must build and pass its relevant checks.

## Review Focus

1. Pending reimport while the browser is open: stale success cannot activate a different pending revision (Task 2/4 tests).
2. An old refresh returns after timeout or after a newer refresh commits: cancellation/deadline/revision checks refuse cache writes and late leases despite unchanged generation (Task 2/4/5 tests).
3. Missing `oid` on refresh despite successful initial sign-in: reject before STS and preserve the previous protected cache (Task 3/4 tests).
4. Existing Vertex Chirp at activation: retire without replacement credential resolution; failure blocks leases and is reported with committed state; concurrent startup cannot reinstall a Vertex child (Task 4 tests). Import/failed login still leaves legacy authorization usable (Task 2/7 tests).
5. Development imports pass but packaged runtime lacks MSAL: closed readiness error and failed packaging qualification, not an apparent connected state (Task 1/9 tests).

## Files and interface map

New focused Python modules under `mcp_server/src/rook/providers/`:

- `vertex_workforce_contract.py`: immutable settings, private principal/assertion, candidate and credential-context types; canonical validation and identifiers.
- `vertex_workforce_store.py`: pending/active envelope operations using the existing DPAPI/mutex/atomic-write primitives.
- `vertex_entra.py`: MSAL lifecycle, protected-cache serialization, explicit account selection and independent ID-token verification.
- `vertex_workforce_exchange.py`: pinned SDK supplier/STS exchange, deadlines and project metadata.

Modify existing `vertex_auth.py`, `vertex_backend.py`, `vertex_token_lease.py`; `agent/chat/vertex_configuration_http.py`, `vertex_media_http.py`; `chirp_manager.py` only for workforce refusal/recycling. Keep shared text-call sites using `apply_vertex_litellm_arguments`.

Managed modifications: `src/Rook/Services/Vision/Image/Vertex/VertexAccessTokenContract.cs`, `src/Rook/UI/Chat/ChatServiceVertexAccessTokenSource.cs`, `AgentChatClient.VertexConfiguration.cs`, `RookChatConfigurationDialog.Vertex.cs`, `src/Rook/Services/Vision/Generation/Vertex/VertexMediaTransport.cs`, `src/Rook/Services/Vision/Image/Vertex/VertexImageProvider.cs`, `src/Rook/Services/Vision/Video/Vertex/VertexVeoClient.cs`. Modify managers/ledgers only if binding round-trip/terminal tests identify necessary changes.

Shared Python types produced before use:

```python
FirmSettings  # frozen; schema_version, label, entra_tenant_id, entra_client_id,
              # organization_id, pool_id, provider_id, project_id,
              # workforce_pool_user_project, quota_project_id: str | None,
              # region, exchange='sts_id_token_v1'
PrivatePrincipal  # frozen; tid, oid, msal_account_key; repr redacted
VerifiedEntraAssertion  # assertion: str (repr=False), principal, expires_at:int
EntraSessionCandidate  # principal, serialized_cache:str (repr=False), assertion, operation_deadline
WorkforceExchangeResult  # access_token (repr=False), expires_at, project_id,
                         # workforce_pool_user_project, quota_project_id;
                         # contains no durable generation/principal ID yet
WorkforceCredentialContext  # access_token (repr=False), expires_at, generation,
                           # principal_id, connection_fingerprint, project_id,
                           # workforce_pool_user_project, quota_project_id
ActivationTicket  # pending_revision:str, authorization_epoch:str
WorkforceActiveRecord  # settings, generation, principal_id, connection_fingerprint,
                       # protected principal/cache/key association, cache_revision:int,
                       # chirp_retirement_pending:bool (true at activation)
ActiveVertexAuthorizationSnapshot = VertexRecord | WorkforceActiveRecord
FirmSignInCheckResult  # contract_version=2, check_scope='identity_exchange', state,
                      # code:str|None, generation:str|None; image_access, video_access,
                      # billing, quota are each the literal 'unverified'; no token
```

New binding version 2 has exactly nine fields: `binding_version`, `authorization_generation`, `principal_id`, `connection_fingerprint`, `project_id`, `workforce_pool_user_project`, `quota_project_id` (nullable), `location`, `model_id`. Version 1 retains exactly its current five fields for legacy providers.

Token request compatibility: existing four-key requests remain v1; new clients add `contract_version: 2`. V2 lease response adds `contract_version: 2` and nullable `quota_project_id` to the current lease data, and uses binding v1 for legacy or v2 for workforce. V2 validation response is exactly `{contract_version: 2, validated: true}`. V1 clients cannot receive a workforce lease: return fixed `vertex_client_upgrade_required` before credential resolution. Do not loosen existing parsers into arbitrary-field acceptance.

### Verification conventions

Run commands from the selected execution checkout. Set `$RookPython` to an existing trusted development interpreter, verified to import the checked-out source through `PYTHONPATH=<checkout>/mcp_server/src`; do not use a private installed release interpreter as a development profile. After Task 1, use the approved locked environment with MSAL. Record interpreter path privately and version in sanitized evidence.

Managed build: `dotnet build src/Rook/Rook.csproj -c Debug --no-restore -p:RhinoPluginDir=` (all configured targets, no installed copy). Focused managed tests: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter 'FullyQualifiedName~Vertex|FullyQualifiedName~GenerationPublicationGuard' --verbosity minimal` without `--no-build`.

Python: `& $RookPython -m pytest <exact test paths> -q`. Expected result is every selected test passed, no hidden skip for the behavior being verified. At each TDD step, observe failure caused by the missing behavior before implementation. Commit only named task files after `git diff --check` and relevant checks; use `git add -f` only for exact ignored documentation files.

## Task 1: Admit pinned MSAL and qualify dependency inputs

**Files:** modify `mcp_server/pyproject.toml`, `mcp_server/uv.lock`, `installer/python-runtime/requirements-third-party-lock.txt`, `scripts/python-runtime/build-rook-python-wheelhouse.ps1`, `scripts/validate-python-wheelhouse.ps1`, and `scripts/tests/python-runtime-packaging.tests.ps1`; add `mcp_server/tests/test_vertex_msal_dependency.py`. Modify `scripts/deploy-local-testing.ps1` import preflight only if its fixed admitted-module list needs MSAL.

**Interfaces:** consumes approved exception; produces importable `msal==1.39.0` with unchanged existing pins and packaged-runtime qualification. Later modules can depend on its public APIs and serializable cache.

- [ ] Add failing test `test_msal_required_scopes_are_added_without_graph`: use the pinned library with synthetic tenant discovery and no network; call `initiate_auth_code_flow([], response_mode='form_post', redirect_uri='http://localhost:<test-port>')`. Assert authorization scopes equal `{'openid','profile','offline_access'}`, PKCE method `S256`, nonempty state/nonce; direct reserved-scope input is not used. `test_packaged_import_gate_requires_msal` must reject a runtime missing MSAL.
- [ ] Run the dependency test and packaging contract script; observe the missing package/preflight behavior. Keep absent-MSAL detection a fixed error, not a fallback.
- [ ] Add `msal==1.39.0`, update the development lock with the existing lock tool, and review its diff. Required MSAL wheel is `msal-1.39.0-py3-none-any.whl`, SHA-256 `2d2577886906cd7293850dffa2da29119966c213bfc6ec0cecf8bf7621e1ca77`, verified against official release metadata during planning. Require actual wheel digest verification when staging; metadata alone is not staged-artifact proof. Preserve the two existing transitive pin profiles; reject unrelated changes. Add import/version checks and manifest evidence to the existing runtime builder/validator.
- [ ] Run `& $RookPython -m pytest mcp_server/tests/test_vertex_msal_dependency.py -q` and `powershell -NoProfile -File scripts/tests/python-runtime-packaging.tests.ps1`. Existing accepted wheel-cache/locked-input tests remain authoritative. Full staged wheelhouse qualification runs in Task 9 after source commits are clean.
- [ ] Commit: `build(auth): admit pinned MSAL for firm sign-in`.

## Task 2: Define contracts and separate pending settings from active authorization

**Files:** create `vertex_workforce_contract.py`, `vertex_workforce_store.py`, `mcp_server/tests/test_vertex_workforce_store.py`; modify `vertex_auth.py`, `test_vertex_auth.py` for envelope delegation and mode validation.

**Interfaces:** `parse_firm_settings(raw: bytes) -> FirmSettings`; `VertexWorkforceStore.import_pending(settings: FirmSettings) -> ActivationTicket`; `read_pending() -> tuple[FirmSettings, ActivationTicket] | None`; `activate(ticket: ActivationTicket, candidate: EntraSessionCandidate, exchange: WorkforceExchangeResult, *, cancel_check: Callable[[], None]) -> WorkforceCredentialContext`; `discard_pending() -> None`; `disconnect_all() -> None`; `snapshot_active() -> ActiveVertexAuthorizationSnapshot | None`; `load_active_session(expected_generation: str) -> tuple[FirmSettings, PrivatePrincipal, str, int]` (settings, principal, serialized cache, cache revision); `commit_refreshed_cache(expected_generation: str, expected_cache_revision: int, principal: PrivatePrincipal, serialized_cache: str, *, deadline: float, cancel_check: Callable[[], None]) -> int` (new revision); `mark_chirp_retired(expected_generation: str, *, deadline: float, cancel_check: Callable[[], None]) -> None`. The store builds opaque identity IDs/fingerprints internally; callers cannot choose their values. The post-activation context remains in memory; the Google bearer is not written into active settings. Its bearer is not eligible for lease issuance until pending retirement is cleared.

- [ ] Add failing `test_import_failure_cancel_and_disconnect_keep_slots_consistent` and `test_v1_active_survives_pending_import`: import must preserve active generation/ciphertext and issue zero recycler calls; failed parsing leaves both slots untouched. Discard leaves active untouched. Disconnect empties both and advances a retained authorization epoch. Reimport invalidates an earlier ticket. `test_same_employee_reconnect_rotates_generation` asserts rotation only on activation.

  Required assertions against the synthetic store fixture:

  ```python
  prior = store.snapshot_active()
  ticket = store.import_pending(settings)
  assert store.snapshot_active() == prior
  store.disconnect_all()
  assert store.read_pending() is None and store.snapshot_active() is None
  with pytest.raises(VertexAuthError):
      store.activate(ticket, candidate, exchange, cancel_check=lambda: None)
  ```
- [ ] Add failing `test_cache_commit_rejects_cancelled_or_expired_worker` and `test_old_cache_revision_cannot_overwrite_new_refresh`, using an injected monotonic clock and cancellation event. Hold revision N, successfully commit N+1, then attempt the old write with the same generation/principal; assert fixed `vertex_refresh_stale`, unchanged N+1 ciphertext/revision and no merging. Expired/cancelled writes must be refused after lock acquisition and before replacement. Test activation starts with pending retirement and generation-conditional clearing cannot clear a newer session's flag.

  ```python
  revision = store.load_active_session(generation)[3]
  newer = store.commit_refreshed_cache(generation, revision, principal, new_cache,
      deadline=deadline, cancel_check=check_new_worker)
  with pytest.raises(VertexAuthError) as denied:
      store.commit_refreshed_cache(generation, revision, principal, old_cache,
          deadline=deadline, cancel_check=check_old_worker)
  assert denied.value.code == 'vertex_refresh_stale'
  assert store.load_active_session(generation)[2:] == (new_cache, newer)
  ```
- [ ] Run `& $RookPython -m pytest mcp_server/tests/test_vertex_workforce_store.py mcp_server/tests/test_vertex_auth.py -q`; observe missing contracts/behavior, including revision/deadline/retirement assertions.
- [ ] Define immutable types and the version-2 envelope `authorization_epoch`, `pending`, `active`. Use existing mutation/DPAPI/atomic-write patterns; preserve embedded legacy active record generation. Implement compare-and-swap activation, strict bounds/duplicate-key refusal, protected identity association and keyed settings fingerprint. Cache writes increment a nonnegative revision under the mutation lock after checking principal/generation/revision, cancellation and deadline; reread current envelope before modifying only the cache fields. Cache-only refresh changes no authorization generation/epoch. Activation sets pending retirement; clearing it requires matching generation and verified lifecycle completion, never a cache-only update. Provide legacy mode delegation so every earlier auth test passes before later consumers use these contracts.
- [ ] Run those tests plus store write-failure, future-schema, oversized-cache/envelope, cancelled mutex-wait and interrupted atomic-write cases. Verify no plaintext serialized cache in store bytes/repr.
- [ ] Commit: `feat(auth): separate pending firm settings and active session`.

## Task 3: Implement MSAL sign-in and verified principal continuity

**Files:** create `vertex_entra.py`, `mcp_server/tests/test_vertex_entra.py`; reuse callback lifecycle utilities from `vertex_oauth.py` by a small local extraction only if necessary; rerun `test_vertex_oauth.py` for any extraction.

**Interfaces:** `EntraSessionAdapter.begin(settings: FirmSettings, ticket: ActivationTicket, *, cancel_check: Callable[[], None]) -> EntraSessionCandidate`; `EntraSessionAdapter.refresh(settings: FirmSettings, serialized_cache: str, expected: PrivatePrincipal, *, deadline: float, cancel_check: Callable[[], None]) -> EntraSessionCandidate`; `EntraSessionAdapter.verify_assertion(raw: str, settings: FirmSettings, *, expected_nonce: str | None, expected_principal: PrivatePrincipal | None, deadline: float, cancel_check: Callable[[], None]) -> VerifiedEntraAssertion`. Cache text is already unprotected only inside Python; never export it to C#. Pass the operation's cancellation/deadline through the bounded MSAL discovery/token and JWKS transports, checking before dispatch and after response.

- [ ] Add failing signed synthetic-token tests: `test_missing_oid_stops_before_exchange`, `test_missing_tid_stops_before_exchange`, `test_refresh_missing_oid_preserves_cache`, `test_refreshed_tid_oid_must_match`, `test_wrong_nonce_and_replayed_callback_rejected`. Assertions: no returned candidate/token on failure, cache bytes unchanged, zero Google calls. Verify issuer/audience/signature/time with an injected clock and synthetic keys.

  ```python
  with pytest.raises(VertexAuthError):
      adapter.verify_assertion(signed_missing_oid, settings,
          expected_nonce=nonce, expected_principal=None, deadline=deadline,
          cancel_check=check_worker)
  assert google_calls == []
  assert persisted_cache == prior_cache
  ```
- [ ] Run `& $RookPython -m pytest mcp_server/tests/test_vertex_entra.py -q`; observe missing adapter.
- [ ] Wrap `PublicClientApplication`/`SerializableTokenCache`, tenant authority, broker-disabled configuration, empty resource scopes and the public auth-code-flow APIs. Rook owns a bounded POST loopback listener and cancellation; MSAL owns flow/grant state. Validate claims/signature independently with existing PyJWT/cryptography and pinned tenant keys; require GUID `tid`/`oid`. Force silent refresh only for the explicitly bound MSAL account; never pick the first account or return a cached expired ID token as a fresh assertion.
- [ ] Test 180-second interaction deadline, 30-second refresh aggregate, <=20-second request, <=1 MiB responses, <=60-second time tolerance, one bounded unknown-key refresh, wrong callback host/path/port, invalid form/duplicate parameters, no redirects, PII logging disabled, cache <=256 KiB. Entra errors expose only fixed public codes. Test cancellation at callback, token response and cache serialization; no late durable write.
- [ ] Run `test_vertex_entra.py`, `test_vertex_msal_dependency.py`, `test_vertex_oauth.py`; commit `feat(auth): add verified Entra desktop session adapter`.

## Task 4: Pin SDK STS exchange, activation and stop-only Chirp retirement

**Files:** create `vertex_workforce_exchange.py`, `mcp_server/tests/test_vertex_workforce_exchange.py`; modify `vertex_backend.py`, `vertex_auth.py`, `chirp_manager.py`; extend `test_vertex_backend.py`, `test_vertex_auth.py`, `test_vertex_workforce_store.py`, `test_chirp_manager.py`, `test_vertex_runtime_integration.py`.

**Interfaces:** `exchange_assertion(settings: FirmSettings, assertion: VerifiedEntraAssertion, *, deadline: float, cancel_check: Callable[[], None], request: object | None = None) -> WorkforceExchangeResult`; `connect_vertex_workforce(ticket: ActivationTicket, *, store: VertexWorkforceStore, entra: EntraSessionAdapter, cancel_check: Callable[[], None], retire: Callable[[str, float, Callable[[], None]], None]) -> VertexOperationResult`; `refresh_vertex_workforce(*, store: VertexWorkforceStore, entra: EntraSessionAdapter, expected_generation: str, deadline: float, cancel_check: Callable[[], None]) -> WorkforceCredentialContext`; `chirp_manager.retire_after_workforce_commit(expected_generation: str, deadline: float, cancel_check: Callable[[], None]) -> None`; `vertex_backend.finish_workforce_retirement(*, store: VertexWorkforceStore, expected_generation: str, deadline: float, cancel_check: Callable[[], None], retire: Callable[[str, float, Callable[[], None]], None]) -> None`. The production retire callback obtains the current store snapshot rather than replacement credentials. Exchange returns only bearer/expiry/project roles; Task 2 activation creates the durable binding and pending retirement flag. The backend retires then generation-conditionally clears the flag. Refresh refuses pending retirement, loads the bound cache/revision, verifies principal, exchanges, commits using Task 2's revision/deadline/cancellation checks and rechecks active context before returning a lease candidate.

- [ ] Add failing `test_sts_id_token_contract_has_no_client_auth` with fake SDK transport. Assert exact endpoint, token-exchange grant, workforce audience, `cloud-platform`, ID-token subject type, access-token requested type, decoded SDK `options.userProject`, no Authorization/client ID/client secret, one call and preserved quota metadata. Add response expiry/type/body bounds and STS refusal cases.

  ```python
  assert captured.url == 'https://sts.googleapis.com/v1/token'
  assert captured.form['grant_type'] == 'urn:ietf:params:oauth:grant-type:token-exchange'
  assert captured.form['subject_token_type'] == 'urn:ietf:params:oauth:token-type:id_token'
  assert 'authorization' not in {name.lower() for name in captured.headers}
  assert not {'client_id', 'client_secret'} & captured.form.keys()
  ```
- [ ] Add held-response races: `test_failed_login_preserves_active_after_import`, `test_cancel_after_exchange_cannot_activate`, `test_reimport_rejects_late_exchange`, `test_disconnect_rejects_late_exchange`, `test_active_save_rejects_candidate`. Assert active bytes/generation unchanged except deliberate mutations, no candidate cache merging, and zero late recycler/activation.
- [ ] Add `test_timed_out_refresh_cannot_write_or_return_context` and `test_old_refresh_returns_after_newer_commit`: hold the old Entra/STS response, revoke its cancellation event/deadline, complete a newer refresh with unchanged generation, then release the old worker. Assert no further Google dispatch, no old cache/context return, and N+1 cache/revision preserved. Releasing the old worker must settle, not leave an unobserved thread exception.
- [ ] Add `test_workforce_activation_retires_without_resolving_bootstrap`, `test_workforce_retirement_failure_keeps_committed_state`, `test_vertex_startup_racing_activation_cannot_reinstall_child`, `test_workforce_text_refused_before_adc_or_child_start`. Test no-child success, verified event/forced retirement, unowned/still-live failure, no replacement credential lookup or child startup, and legacy/non-Vertex behavior. A pre-activation Entra/STS failure must issue zero retire calls.

  ```python
  assert bootstrap_calls == [] and replacement_starts == []
  assert success_result.success and retired_pid == prior_owned_pid
  assert successful_store.snapshot_active().chirp_retirement_pending is False
  assert failure_result.code == 'vertex_restart_required'
  assert failed_store.snapshot_active().generation == failure_result.generation
  assert failed_store.snapshot_active().chirp_retirement_pending is True
  with pytest.raises(VertexAuthError):
      refresh_vertex_workforce(store=failed_store, entra=entra,
          expected_generation=failure_result.generation, deadline=deadline,
          cancel_check=check_worker)
  ```
- [ ] Run `& $RookPython -m pytest mcp_server/tests/test_vertex_workforce_exchange.py mcp_server/tests/test_vertex_backend.py mcp_server/tests/test_vertex_workforce_store.py mcp_server/tests/test_chirp_manager.py mcp_server/tests/test_vertex_auth.py mcp_server/tests/test_vertex_runtime_integration.py -q`; observe missing exchange, retirement and late-worker protections.
- [ ] Construct pinned `identity_pool.Credentials` using a Rook supplier that accepts only a verified assertion; preserve SDK form encoding. Share the existing aggregate deadline and disable redirects/implicit HTTP retries through the request adapter. Check cancellation/deadline at network boundaries, cache commit and final context return; never retry stale cache commits. Initial sign-in/exchange works entirely in the candidate cache; activation commits before stop-only retirement. Carry the candidate's absolute operation_deadline through exchange, activation and retirement; do not reset it after Entra token acquisition. Keep exchange/commit/retirement within the 30-second post-browser phase; existing retirement waits (10 seconds graceful, 2 seconds forced) are capped by remaining time.
- [ ] Install workforce guards now in `apply_vertex_litellm_arguments`, legacy text readiness/token loading, `_resolve_vertex_bootstrap`, live discovery reuse and every child-launch path. Use fixed `vertex_text_federation_unsupported` with zero ADC fallback. Add the stop-only path under the existing replacement lock, reusing `_retire_discovered_process` and exact ownership checks before any replacement credential resolution; conservatively retire the existing managed sidecar, never start its replacement. Launch/reuse rechecks mode/generation under that lock; cap lock acquisition and waits by remaining time, avoid nested acquisition of the non-reentrant lock, and never hold the store mutation lock during retirement. Retirement failure preserves pending retirement and committed generation, reports `vertex_restart_required`, and blocks workforce leases. `finish_workforce_retirement` supports verified retry through Task 7's explicit check, including after restart; passive status/startup cannot clear the flag. Non-Vertex startup uses its normal path with no Vertex bootstrap after retirement.
- [ ] Run those tests plus `test_vertex_entra.py`, `test_chirp_manager.py`, `test_vertex_auth.py`, `test_vertex_runtime_integration.py`; commit `feat(auth): activate firm sessions with STS and verified Chirp retirement`.

**Identity checkpoint:** inspect actual scopes/claims, mock STS wire evidence, encrypted persistence, cache-revision and expired-worker refusal, and stop-only retirement ordering/failure/recovery. Confirm no executable path can activate workforce credentials before its text/Chirp guards exist. Do not advance with an unexplained grant mismatch or an old sidecar reported retired without evidence. Record that SDK construction passed while real exchange remains not run.

## Task 5: Extend lease contracts and consumers before media transport

**Files:** modify `vertex_token_lease.py`, `agent/chat/vertex_media_http.py`, `VertexAccessTokenContract.cs`, `ChatServiceVertexAccessTokenSource.cs`; tests `test_vertex_token_lease.py`, `test_vertex_media_http.py`, `ChatServiceVertexAccessTokenSourceTests.cs`. Add `src/Rook.Tests/Services/Vision/Generation/VertexBindingV2Tests.cs`.

**Interfaces:** preserve `IVertexAccessTokenSource.AcquireAsync(model, location, expectedBinding, ct)` / `ValidateBindingAsync(binding, ct)`; extend managed `VertexAuthorizationBinding` with nullable legacy-compatible principal/fingerprint/user/quota-project properties and versioned closed serializers. `VertexAccessTokenLease` gains `ContractVersion` and `QuotaProjectId`. Python `VertexTokenLeaseService.acquire` gains `contract_version: int = 1`; its workforce loader calls Task 4's `refresh_vertex_workforce` with a per-worker thread-safe cancellation check, not the legacy ADC loader. V1 behavior remains testable.

- [ ] Add failing Python `test_same_principal_refresh_preserves_v2_binding`, `test_validate_checks_owned_principal_without_refresh`, `test_old_client_cannot_acquire_workforce_lease`; managed `V2Lease_RejectsQuotaAndPrincipalMismatch`, `V1Binding_RoundTripsWithoutExtraFields`, `ValidationV2_UsesClosedShape`. Assert exactly nine v2 binding fields, fixed upgrade error, no token on mismatch.

  ```python
  assert refreshed.binding == initial.binding
  assert refreshed.generation == initial.generation
  with pytest.raises(VertexAuthError) as denied:
      await service.acquire(model, location, initial.binding, contract_version=1)
  assert denied.value.code == 'vertex_client_upgrade_required'
  ```
- [ ] Add `test_acquire_timeout_revokes_worker_before_unlock`, `test_old_thread_cannot_cache_lease_after_newer_refresh`, `test_retirement_pending_blocks_cached_and_fresh_lease`: hold old thread completion, time out the async caller, complete a newer acquire, then release/observe the old worker. Assert cancellation is set before async lock release, zero old cache writes/lease installation and preserved newer revision/token cache. Cover caller cancellation and disconnect in addition to deadline expiry.
- [ ] Run both Python files and focused managed tests without `--no-build`; observe missing contracts and async revocation/retirement protection.
- [ ] Define contracts and update Python/C# parsers, failure mappings and test fakes in the same commit. Recheck active context and pending retirement before cached reuse, before/after refresh and validation-only publication calls. Set the per-worker cancellation event in timeout/cancellation handling before releasing the async lock; retain/observe the underlying worker until settled without extending the caller's 30-second ceiling. The thread receives the absolute deadline and cancel check; revoked results cannot enter `_cached_lease`. Refresh persistence uses Task 2's generation/principal/cache-revision transaction. Validate quota/project values and binding consistency. Legacy ADC remains legacy, never a workforce fallback.
- [ ] Build all managed Debug targets and run the focused managed command; run `test_vertex_token_lease.py`, `test_vertex_media_http.py`, `test_vertex_auth.py`. Ensure existing callers compile before Task 6 uses new fields.
- [ ] Commit: `feat(auth): carry firm identity and projects through versioned leases`.

## Task 6: Apply quota metadata and strengthen publication/race proof

**Files:** modify `VertexMediaTransport.cs`, `VertexImageProvider.cs`, `VertexVeoClient.cs`; tests `VertexImageProviderTests.cs`, `VertexVeoTests.cs`, `VertexVeoManagerAcceptanceTests.cs`, `VertexTestFixtures.cs`, `VertexBindingV2Tests.cs`. Inspect `ImageJobManager.cs`, `VideoJobManager.cs` and JSONL ledgers; change only where needed to preserve binding-v2 metadata/terminal guards.

**Interfaces:** `VertexMediaTransport.PostAsync(VertexAccessTokenLease lease, string action, string body, long responseLimit, bool submission, CancellationToken ct, Action? beforeDispatch = null) -> Task<VertexHttpResult>` replaces the internal binding/token argument pair; update every caller/test in this task. Both providers use the identical lease context for destination, authorization and permitted quota header; publication still calls `ValidateBindingAsync`.

- [ ] Add failing `FirmQuotaHeader_IsBoundOnSubmitAndEveryPoll`, `DisconnectDuringCompletion_CannotPublish`, `SameEmployeeReconnect_RejectsOldOperation`, `V2Metadata_SurvivesLedgerRestart`. Assertions: header only `x-goog-user-project` when configured, no arbitrary forwarding; unchanged resource project/model/location/operation; zero publication after interruption; no auto requests after restart.

  ```csharp
  Assert.Equal("synthetic-firm-project", sent.Headers.GetValues("x-goog-user-project").Single());
  Assert.Equal(VideoJobState.Interrupted, stopped.State);
  Assert.Empty(publishedArtifacts);
  Assert.Equal(1, submissionCount);
  ```
- [ ] Run focused managed tests and observe missing quota/binding behavior.
- [ ] Update transport and both provider consumers together. Keep one dispatch per submit, disabled redirects, capped output and unchanged inline MP4 pipeline. Validate nullable quota header against lease binding before any send. Reuse current guards; do not weaken terminal transitions to accommodate v2. Legacy completed artifacts remain readable; interrupted legacy operations are never upgraded to a new firm binding.
- [ ] Run fresh build/focused managed tests, held refresh/poll/publication response fixtures, stop/completion races and ambiguous-submit/restart tests. Token/quota mismatch must produce zero HTTP calls.
- [ ] Commit: `feat(vision): bind firm media requests and publication to lease context`.

**Publication checkpoint:** inspect request counts and gate placement in real consumers, not only fake token-service tests. Confirm local stop is still `LocalStopOnlyOutcome`, no remote-cancel claim, no duplicate billed retry and no terminal overwrite.

## Task 7: Expose pending/active firm settings and identity-only sign-in checks

**Files:** modify `vertex_configuration_http.py`, `vertex_backend.py`, `AgentChatClient.VertexConfiguration.cs`, `RookChatConfigurationDialog.Vertex.cs`. Extend `test_vertex_configuration_http.py`, `test_vertex_media_ui.py`, `test_vertex_backend.py`, `test_vertex_runtime_integration.py`, `test_chirp_manager.py`, `VertexConfigurationClientTests.cs`, `VertexConfigurationDialogTests.cs`. Task 4 already owns text/Chirp refusal and retirement; rerun its regression tests here.

**Interfaces:** add closed owned-route operations `import_firm {operation,settings_path}`, `discard_firm {operation}`, `connect_firm {operation,pending_revision,authorization_epoch}`, `firm_status {operation}`, `check_firm_sign_in {operation,authorization_generation}`, `prepare_firm_reconnect {operation,authorization_generation}`. Reconnect preparation copies active settings to a fresh pending revision without rotating authorization; pending mutations honor cancellation/deadline immediately before replacement. Legacy browser consent waits outside the credential mutex and uses captured-epoch conditional activation; version-2 disconnect retains a tombstone. Existing legacy operations retain their closed shapes. `ReadFirmConfigurationAsync(ct)`, `ImportFirmSettingsAsync(path, ct)`, `DiscardPendingFirmSettingsAsync(ct)`, `ConnectFirmAccountAsync(pendingRevision, authorizationEpoch, ct)` return typed firm status with pending/active summaries. `vertex_backend.check_firm_sign_in(expected_generation: str, *, store: VertexWorkforceStore, entra: EntraSessionAdapter, deadline: float, cancel_check: Callable[[], None], retire: Callable[[str, float, Callable[[], None]], None]) -> FirmSignInCheckResult` uses Task 4 retirement/forced refresh, not a cached lease or model probe. Managed `CheckFirmSignInAsync(expectedGeneration, ct)` returns the closed result defined in Task 2. Existing `disconnect` clears both slots. Summaries/results contain no tenant/object IDs, MSAL cache, assertion or bearer.

- [ ] Add failing `test_pending_import_is_not_connected_and_never_refreshes`, `test_failed_connect_keeps_legacy_chirp_usable`, `test_disconnect_clears_pending_and_rejects_late_callback`; managed `PendingFirmSettings_AreDistinctFromConnectedAccount`, `FirmConnect_UsesDisplayedRevision`. Assert no session mutation on passive read/import, explicit limitation before activation, no Google desktop JSON field in firm view. Rerun Task 4's workforce text/Chirp refusal tests.

  ```python
  assert store.snapshot_active().generation == legacy_generation
  assert refresh_calls == [] and recycler_calls == []
  with pytest.raises(VertexAuthError) as denied:
      apply_vertex_litellm_arguments('vertex_ai/gemini-2.5-flash', {}, store=workforce_store)
  assert denied.value.code == 'vertex_text_federation_unsupported'
  assert adc_calls == [] and child_starts == []
  ```
- [ ] Add `test_sign_in_check_success_leaves_models_billing_quota_unverified`, `test_sign_in_check_never_dispatches_model_requests`, `test_sign_in_check_timeout_or_disconnect_discards_success`; managed `SignInCheck_RejectsReadyOrVerifiedClaims`, `SignInCheck_MapsClosedFailureStates`. Use held Entra/STS responses, pending-retirement recovery and authorization-generation mismatch. Assert one real mock Entra refresh and STS call on success, no browser/text/model/submit/poll/fetch calls, and no successful UI state after cancellation.

  ```python
  assert result.check_scope == 'identity_exchange'
  assert result.state == 'signed_in'
  assert (result.image_access, result.video_access, result.billing, result.quota) == ('unverified',) * 4
  assert model_calls == [] and browser_calls == []
  ```
- [ ] Run the listed Python configuration/backend/Chirp tests and focused managed configuration tests; observe missing sign-in-check operation, closed result/state mapping and cancellation protections.
- [ ] Wire existing session-nonce admission to Task 4 without exposing a public token export. Show active/pending settings, discard/reconnect and restart-required states separately. Keep legacy `save` refused in active workforce mode with `vertex_firm_settings_reimport_required`; use pending reimport/reactivation. Preserve shared-region and non-Vertex behavior. Disclose media-only limitation before activation, not after it.
- [ ] Keep the check's thread-safe cancellation/deadline semantics through the owned route: return fixed timeout within 30 seconds, observe the retained worker asynchronously, and keep its mutation slot busy until it settles. Do not await the current unbounded `shield(worker)` cleanup before returning a timed-out check. Disconnect can set cancellation and invalidate the store/tombstone immediately even while a worker is outstanding; it cannot be rejected merely as configuration busy. Late results neither restore success nor clear a newer worker's slot. Add route-level held-worker tests for these cases.
- [ ] Implement **Check sign-in** with a 30-second aggregate deadline shared across stop-only recovery, forced Entra refresh, STS and result validation. Closed states: `signed_in`, `sign_in_required`, `exchange_denied`, `service_unavailable`, `authorization_changed`, `restart_required`; image/video/billing/quota are always literal `unverified`. No network on passive status, no model readiness endpoint and no **Generation ready** claim after STS. Success copy: **Sign-in and Google exchange passed. Image/video access, billing and quota remain unverified.** Errors use fixed public codes; state/code mismatches or a different returned generation are rejected by C#. Checking state is transient; timeout cannot restore the previous successful check as current.

  Closed state/code mapping: `signed_in` -> null; `sign_in_required` -> `vertex_firm_sign_in_required`; `exchange_denied` -> `vertex_workforce_exchange_denied`; `service_unavailable` -> `vertex_token_issuance_timeout`, `vertex_request_failed` or `vertex_refresh_stale`; `authorization_changed` -> `vertex_authorization_changed`; `restart_required` -> `vertex_restart_required`. Add these fixed codes at their owning auth operations and bridge whitelist; raw provider bodies never become a code/message. A failed check can report only the captured generation, or null after local deletion, never a replacement connection.
- [ ] Run those tests plus full Vertex Python tests, `test_vertex_oauth.py`, managed settings tests and all affected builds. Verify browser cancellation cleanup, wrong nonce/Origin/extra keys, version-1 migration, no billed passive probe, and existing manager restart semantics.
- [ ] Commit: `feat(ui): add firm settings and identity-only sign-in checks`.

**Configuration checkpoint:** inspect pending/active UI copy, atomic activation/retirement evidence, import/failure/cancel/disconnect tests, shared text/Chirp compatibility and **Check sign-in** request counts. STS success must leave both models, billing and quota unverified in the actual managed view.

## Task 8: Document firm administration and private acceptance evidence

**Files:** modify `docs/guides/enterprise-google-media-setup.md`, `scripts/vertex_media_acceptance.py`, `mcp_server/tests/test_vertex_media_acceptance_harness.py`; create `docs/guides/enterprise-google-workforce-setup.md`, `docs/superpowers/reports/2026-10-05-enterprise-google-workforce-verification.md`. Synthetic fixtures stay in tests; actual setup remains outside Git.

**Interfaces:** extend the existing `live_acceptance(evidence)` function without changing its legacy evidence result shape. Its versioned workforce evidence section recognizes adapter/exchange, opaque principal/project labels, installed runtime pins, pending/active lifecycle, real Entra/STS refresh counts and bill attribution status. It validates evidence; it does not run Google jobs or authorize spend.

- [ ] Add failing `test_workforce_evidence_requires_real_refresh_and_project_attribution`, `test_inconclusive_intervention_is_not_pass`, `test_missing_live_prerequisites_cannot_be_pass`, `test_private_sentinels_rejected`. Retain all earlier Google-account evidence requirements.
- [ ] Run `test_vertex_media_acceptance_harness.py`; observe missing workforce fields/status rules.
- [ ] Update validator and guides with a synthetic non-secret firm settings example matching `FirmSettings`. Document Entra public desktop registration, `profile`/stable `oid` mapping, pool client-ID audience, group/IAM setup, project roles, direct usage costs, broker-dependent Conditional Access limitation, media-only boundary, pending activation, retirement-failure recovery, disconnect and remote billing behavior. **Check sign-in** verifies identity/exchange only; live output/billing evidence remains separate. Existing Google account pilot remains its own procedure; no Advanced Protection bypass advice.
- [ ] Run validator tests and scan committed docs/fixtures for held private identifiers/credentials without printing them. Record automated and installed cases separately; incomplete private billing evidence is pending, not passed.
- [ ] Commit: `docs(auth): document firm setup and workforce acceptance`.

## Task 9: Fresh verification, packaged runtime and independent review

**Files:** report from Task 8; existing wheelhouse/deploy/release scripts only if a concrete failure requires a scoped fix. Product changes triggered by a review return to their owning task/test cycle.

**Interfaces:** produces exact tested commit, fresh managed/Python results, reviewed dependency diff, staged artifact hashes/imports and independent authentication/whole-branch findings. This is automated/package acceptance, not Google live acceptance.

- [ ] Rebuild Debug and Release managed targets with `-t:Rebuild -p:RhinoPluginDir=` before final tests. Enumerate `$workforceVertexTests = @(rg --files mcp_server/tests -g 'test_vertex*.py')`, then run `& $RookPython -m pytest @workforceVertexTests mcp_server/tests/test_chirp_manager.py -q`; no unexpanded Windows wildcard. Run the full managed test suite without `--no-build`; report the known external Prime fixture `Task7_original_producer_values_survive_managed_http_parser` separately if still unavailable, with its exact cause. Never fabricate its dependencies or call the unexcluded gate passed.
- [ ] Verify a clean source commit, then use `scripts/python-runtime/build-rook-python-wheelhouse.ps1` with explicit version, matching Chirp source, staged runtime and accepted dependency wheel cache. Keep evolving Task 9 evidence outside Git until this clean-source build finishes. Use its existing pinned runtime/wheelhouse contract and `scripts/validate-python-wheelhouse.ps1`; run offline installation/import/version/`pip check` verification for MSAL, Google auth and their required dependencies. Missing runtime/accepted wheels is a recorded package prerequisite, not permission for a dependency fallback. Do not silently fall back to a development interpreter and call it packaged qualification.
- [ ] Run existing packaging/locked-input tests with their documented environment variables. Verify no broker extras, exact MSAL wheel digest, staged source commit and manifest imports, and review all dependency changes. Re-run inline-memory measurement only if output parsing/limits/allocation paths changed; preserve the earlier measurement's scope if they did not.
- [ ] Request an independent authentication/whole-branch review after fresh checks. Reviewer examines MSAL scopes/public APIs, assertion validation, STS wire contract, cache-revision/cancellation/deadline checks, stop-only retirement and failure recovery, identity-only UI claims, project/header rules, publication races, legacy regressions and staged dependencies. Resolve actionable findings with focused commits and relevant fresh checks; no live acceptance before this gate.
- [ ] Commit sanitized evidence: `test(auth): record fresh workforce and runtime verification`. Report passed/failed/not-run gates accurately.

## Task 10: Installed firm acceptance after prerequisites and spend approval

**Files:** private evidence and settings only under a user-approved AppData directory outside all Git worktrees; append only scanned, sanitized summary to the report. No actual OAuth/MSAL configuration committed.

**Interfaces:** consumes reviewed source/runtime, approved Entra/pool/project setup, two permitted test identities and explicit generation budget; produces observed live results using the existing RookVision UI.

- [ ] Read/apply `rook:deploy-local-testing`; confirm Rhino and relevant Rook processes are closed, then deploy fresh managed artifacts and the qualified Python payload through the authority script. Verify installed manifests actually select that payload and dependency pins. Preserve existing AppData credentials; never reuse the earlier reserved-release-interpreter development-profile mistake.
- [ ] Import private firm settings and complete normal browser login. Demonstrate pending versus active state, failed/cancelled login preservation, correct `tid`/`oid` continuity and real no-secret STS exchange. Record that the employee created no Google consumer account. Do not auto-grant IAM, create cloud apps or change Conditional Access.
- [ ] After explicit spend approval, submit one image and three supported short videos: completion/forced Entra+STS refresh, active disconnect, active restart. Use source-only invalidation of cached assertions/lease for refresh, not altered signed tokens. Verify image dimensions, video hash/bytes/duration/dimensions, frame decode and RookVision playback. No extra billed attempt if an intervention is missed.
- [ ] Switch between the two approved Entra identities and validate the old interrupted binding through a local controlled fixture without another media submission. Observe administrator-approved denied identity/permission behavior; record actual policy propagation rather than claiming immediate revocation. Confirm resource/user/quota project attribution privately in Cloud audit/billing reports; leave billing status pending until observable.
- [ ] Record exact installed/source/runtime hashes, models/locations, opaque labels, request/refresh counts, ledger transitions and pass/fail/inconclusive/not-run. Scan evidence against private values locally; commit only the sanitized summary. Feature completion requires all required automated, packaged and installed live criteria; do not replace missing live proof with mock results.

## Self-review and handoff

Dependency order is deliberate: Task 1 admits the library; Task 2 defines types/revisioned store transactions; Task 3 defines verified Entra sessions; Task 4 enables exchange/activation together with text/Chirp guards and stop-only retirement; Task 5 defines lease contracts/consumers and async worker revocation; Task 6 uses those contracts for media; Task 7 exposes completed operations and identity-only checks; Task 8 specifies evidence; Task 9 rebuilds/packages/reviews; Task 10 proves live behavior. Every commit must remain independently buildable and pass relevant checks.

Coverage maps spec sections 1-4 to Tasks 1/3/4/8; section 5 to Task 2; section 6 to Tasks 2-5; sections 7-8 to Tasks 4-7; section 9 to Task 7; section 10 to Tasks 1-9; section 11 to Tasks 8-10. All five Review Focus conditions have named owning tests. No implementation skill, dependency installation, Cloud permission grant or billed generation has been invoked while writing this plan.

Review the revised STS decision, media-only text/Chirp boundary and this plan before implementation. Native execution is preserved; the existing explicit MSAL exception is not permission to use Cloud OAuth Preview or to skip review/acceptance.
