# Grasshopper Component Discovery Coherence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace registration-order Grasshopper discovery and split Python/knowledge name resolution with one native-ranked, GUID-custodied, provenance-bearing discovery and metadata transaction.

**Architecture:** `GrasshopperHandler` remains the sole live catalog, selector-resolution, provenance, implementation, and Params owner. Python validates one selector family, forwards one body, verifies correlation, and adds legacy names-only summaries; the bridge stays a byte-preserving delegate. `ToolDispatcher` preserves direct-call arguments and `KnowledgeInjector` skips the two authoritative tools.

**Tech Stack:** C# net48/net8 reflection over Grasshopper 8, `System.Text.Json`, xUnit; Python 3.12, MCP SDK, pytest.

## Global Constraints

- Treat specification commit `411613d7` as the contract authority. Begin implementation
  from the clean, independently approved plan-commit descendant on branch
  `codex/grasshopper-component-discovery-coherence-production-design`, and verify
  `411613d7` remains its ancestor.
- The authoritative contract is `docs/superpowers/specs/2026-08-08-grasshopper-component-discovery-coherence-design.md`.
- Production changes are limited to exactly four existing owners:
  - `src/Rook/Handlers/GrasshopperHandler.cs`
  - `mcp_server/src/rook/server.py`
  - `mcp_server/src/rook/agent/tool_dispatcher.py`
  - `mcp_server/src/rook/learning/knowledge_injector.py`
- Add no production module, endpoint, registry, cache, identity framework, persistent catalog, or external dependency.
- Preserve `audit=true`, `GetComponentParams()`, `gh_edit`, `gh_snapshot`, T*/C*, flows, and receipts.
- Ordinary eligibility is exactly non-obsolete and not hidden. Category matching remains case-insensitive substring matching across Category and SubCategory.
- Search uses one complete native `FindObjects()` acquisition and has no registration-order, knowledge, repeated-over-fetch, or copied-index fallback.
- Search/catalog never instantiate a component, construct `GH_UserObject`, read `Data`, or hash content.
- Metadata makes one managed target call per admitted batch. Python makes no `UnifiedStore` or `/gh/library` selector-resolution call.
- User-object paths and fingerprints appear only in successful selected metadata, never ordinary search candidates.
- Preserve the two documented `TestGHOperationMapping` failures exactly; do not repair or absorb them.
- No model, Rhino, Grasshopper, MCP runtime, or provider contact occurs during implementation or review.
- Report cumulative production additions/deletions at every mandatory review. Stop if a fifth production owner or a new identity abstraction becomes necessary.

## File Map

### Production

- Modify `src/Rook/Handlers/GrasshopperHandler.cs`
  - Native search, deterministic ranking, candidate projection, managed selector resolution, provenance, implementation, Params composition, and per-item/batch outcomes.
- Modify `mcp_server/src/rook/server.py`
  - Public schemas, pre-contact selector validation, one-call forwarding, host-correlation validation, and names-only compatibility summaries.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Direct `gh_library` exact and empty/whitespace argument parity.
- Modify `mcp_server/src/rook/learning/knowledge_injector.py`
  - Explicitly skip authoritative discovery tools.

### Tests

- Create `src/Rook.Tests/Handlers/GrasshopperComponentDiscoveryContractTests.cs`
  - Causal fake component-server coverage for search, metadata, provenance, identity, failure prefixes, and count equations.
- Modify `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
  - Source-bound proof that the metadata body is forwarded unchanged.
- Create `mcp_server/tests/test_grasshopper_component_discovery_coherence.py`
  - Schemas, one-call forwarding, correlation, MCP/gateway semantics, dispatcher parity, and source scans.
- Modify `mcp_server/tests/test_server_component_deprecation.py`
  - Replace knowledge-owned metadata expectations and repair its stale no-contact targeting fixture.
- Modify `mcp_server/tests/test_knowledge_injector.py`
  - Exact skip behavior while preserving the two known unrelated failures.

### Documentation

- Modify `docs/CURRENT_ARCHITECTURE.md`
  - Concise durable ownership statement after implementation is green.
- Modify this plan only for checked steps, observed counts, and review decisions.

## Baseline and Known Test State

The repository Python interpreter is:

```text
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe
```

The pre-implementation adjacent command collected during planning was:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_server_component_deprecation.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_dispatcher_safety.py `
  mcp_server/tests/test_knowledge_injector.py -q
```

Observed result:

```text
325 passed
6 failed
77 warnings
```

Four failures are stale test-targeting setup in `test_server_component_deprecation.py`:

```text
test_gh_edit_attaches_per_item_deprecation_warnings
test_gh_batch_component_info_resolves_active_guid
test_gh_batch_component_info_library_fallback_skips_deprecated_exact_match
test_gh_edit_warns_for_deprecated_nickname_alias
```

Task 3 updates that file's no-contact fixture and replaces the two obsolete metadata
expectations. It does not change `gh_edit` production behavior.

The two separately documented failures that must remain are:

```text
TestGHOperationMapping::test_mapped_tools_return_operation
TestGHOperationMapping::test_mapping_covers_all_categories
```

The fresh worktree does not yet contain .NET restore assets. Before the first managed
RED run, execute one ordinary restore. If restore cannot complete, stop; do not alter
projects or package versions to work around it.

---

### Task 1: Native-ranked live discovery and compact candidate identity

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs:4325-4515`
- Create: `src/Rook.Tests/Handlers/GrasshopperComponentDiscoveryContractTests.cs`

**Interfaces:**
- Consumes: the existing `GetGrasshopperComponentServerNoCanvas()` result and reflected `ObjectProxies`, `FindObjects`, and `CompareProxies` host members.
- Produces: `internal ApiResponse SearchLibraryFromComponentServer(object server, string? search, string? category, int limit, bool exact)` for the ordinary branch; the public `SearchLibrary()` retains the existing audit branch and delegates only non-audit calls.
- Produces candidate JSON fields: `name`, `nickName`, `description`, `category`, `subCategory`, `guid`, `sourceKind`, plus search-only `nativeScore` and `matchSource`.

- [x] **Step 1: Restore the managed test project and record the exact baseline command**

Run:

```powershell
dotnet restore src/Rook.Tests/Rook.Tests.csproj
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore `
  --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~GrasshopperHandlerReadinessTests" `
  --verbosity minimal
```

Record the pass/fail counts and warning count in this plan. Stop on unexplained failures.

Observed on 2026-08-10: restore succeeded; the exact incremental baseline completed with
`88 passed`, `0 failed`, `0 skipped`, and `0 warning lines`.

- [x] **Step 2: Write RED ordinary-discovery contract tests**

Create causal fake host types in the test file. The fake server must expose:

```csharp
public IReadOnlyList<object> ObjectProxies { get; }
public int FindObjects(
    string[] terms,
    int maximumResults,
    out object[] proxies,
    out double[] weights);
public static int CompareProxies(object left, object right);
```

Each fake proxy must expose `Desc`, `Guid`, `LibraryGuid`, `Kind`, `Obsolete`,
`Location`, and a hostile `CreateInstance()` that throws unless a test explicitly permits
metadata. Add named tests proving:

```text
Search_present_calls_FindObjects_once_with_exact_string_and_proxy_count
Search_filters_category_and_exact_before_limit
Search_orders_score_then_CompareProxies_then_guid
Search_rejects_nonfinite_or_misaligned_native_projection
Native_search_or_compare_failure_has_no_fallback_result
Catalog_omitted_or_empty_search_never_calls_FindObjects
Catalog_orders_CompareProxies_then_guid_and_has_no_match_fields
Empty_category_means_no_filter_and_whitespace_category_is_literal
Ordinary_eligibility_excludes_hidden_and_obsolete_only
Exact_name_preserves_native_and_third_party_duplicates
Unknown_kind_fails_without_candidate_list
Search_and_catalog_never_instantiate_or_read_user_object_data
Ordinary_counts_are_complete_and_exact
Audit_branch_shape_and_source_path_remain_unchanged
```

Use synthetic GUIDs and synthetic plugin labels only. Do not use installed Ladybug,
Honeybee, or native component identities as product fixtures.

- [x] **Step 3: Run the new tests and prove RED**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore `
  --filter FullyQualifiedName~GrasshopperComponentDiscoveryContractTests `
  --verbosity minimal
```

Expected: failures because `SearchLibraryFromComponentServer` and the new response fields
do not exist, and current ordinary search truncates registration order.

Observed: `13 failed`, `0 passed`. Every failure was the expected missing
`SearchLibraryFromComponentServer` or `SearchLibraryAuditUnchanged` seam.

- [x] **Step 4: Add the smallest local ordinary-search seam**

Keep `SearchLibrary()` as the public owner:

```csharp
public ApiResponse SearchLibrary(
    string? search,
    string? category,
    int limit = 50,
    bool audit = false,
    bool exact = false)
{
    var componentServer = GetGrasshopperComponentServerNoCanvas();
    if (!componentServer.Success)
        return new ApiResponse { Success = false, Data = componentServer.Error };

    if (audit)
        return SearchLibraryAuditUnchanged(
            componentServer.Server!, search, category, exact);

    return SearchLibraryFromComponentServer(
        componentServer.Server!, search, category, limit, exact);
}
```

`SearchLibraryAuditUnchanged` may be a private extraction of the existing audit body, but
its filtering, counts, ordering, fields, and JSON response shape/values must remain
behaviorally equivalent. Do not route audit through ordinary candidate projection.

- [x] **Step 5: Implement complete native acquisition and deterministic filtering**

The ordinary helper must execute this exact decision:

```csharp
var hasSearch = !string.IsNullOrEmpty(search);
var hasCategory = !string.IsNullOrEmpty(category);

// hasSearch == false: enumerate the complete ObjectProxies snapshot.
// hasSearch == true: invoke FindObjects once with:
//   terms = new[] { search! }
//   maximumResults = complete ObjectProxies.Count
// and require return count, out proxy array, and out score array to agree.
```

Project every proxy strictly before it can enter filtering or ordering. `Kind` admits only
`CompiledObject` and `UserObject`; proxy text values must be strings or actual null as
specified; GUIDs must canonicalize with lowercase `D` format. Any incomplete candidate
fails the whole ordinary operation.

Apply:

```text
not obsolete
AND exposure does not include hidden bit 16
AND optional existing category/subcategory substring filter
AND optional case-insensitive exact Desc.Name filter
```

Then order:

```text
search: native score descending -> CompareProxies -> canonical GUID ordinal
catalog: CompareProxies -> canonical GUID ordinal
```

Apply `limit` only after the complete eligible filtered order exists. Return:

```csharp
new ApiResponse
{
    Success = true,
    Data = new
    {
        Count = returned.Count,
        ReturnedCount = returned.Count,
        TotalMatches = filtered.Count,
        Truncated = returned.Count < filtered.Count,
        Components = returned
    }
};
```

- [x] **Step 6: Run GREEN and the adjacent managed seam**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore `
  --filter "FullyQualifiedName~GrasshopperComponentDiscoveryContractTests|FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~GrasshopperStatusDtoTests" `
  --verbosity minimal
```

Expected: all selected tests pass.

Observed: `80 passed`, `0 failed`, `0 skipped`, and `0 warning lines` on the exact
incremental GREEN command.

- [x] **Step 7: Verify audit and prohibited surfaces mechanically**

Run:

```powershell
rg -n "CreateInstance|GH_UserObject|SHA256|FindAssembly" `
  src/Rook/Handlers/GrasshopperHandler.cs
git diff --check
```

Review the ordinary-search method body and prove none of those metadata operations is
reachable from it. Report production additions/deletions.

Observed: the isolated ordinary-search body contains none of `CreateInstance`,
`GH_UserObject`, `SHA256`, or `FindAssembly`. Task 1 production growth is `340 additions`
and `140 deletions` in the existing managed owner; the net growth is the native search,
strict projection, deterministic ordering, and extracted behavior-equivalent audit seam.

- [x] **Step 8: Commit Task 1**

```powershell
git add src/Rook/Handlers/GrasshopperHandler.cs `
  src/Rook.Tests/Handlers/GrasshopperComponentDiscoveryContractTests.cs `
  docs/superpowers/plans/2026-08-09-grasshopper-component-discovery-coherence.md
git commit -m "feat: rank Grasshopper component discovery natively"
```

**Mandatory review gate:** stop. Independent review must approve native acquisition,
audit isolation, eligibility, candidate shape, deterministic ties, limit ordering, and
the absence of instantiation/hashing before Task 2.

Task 1 review repair on 2026-08-10 tightened `Exposure` to the installed host's enum
representation and replaced the fake integer with an enum. The new raw-integer regression
failed alone before the one-line production correction (`1 failed`, `13 passed`). The
returned-count and exact audit-shape/value regressions were mutation-checked and each
failed when its protected equation was temporarily removed. The restored focused seam
completed with `81 passed`, `0 failed`, and `229` existing compiler/analyzer warning
lines. A clean rebuild completed with `228` repository warnings and `0` errors; no warning
points to the Task 1 test file or newly added discovery lines.

---

### Task 2: Managed selector resolution and source-kind metadata custody

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs:6302-6454`
- Modify: `src/Rook.Tests/Handlers/GrasshopperComponentDiscoveryContractTests.cs`
- Modify: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`

**Interfaces:**
- Consumes: the Task 1 complete live proxy projection and ordinary eligibility rule.
- Produces: `internal ApiResponse HandleBatchComponentInfoFromServer(object server, string body, Func<string, object>? userObjectFactory = null)`.
- Produces exactly one ordered result per admitted selector with the closed status set from the specification.
- Preserves the bridge call `requestJson => Handler.HandleBatchComponentInfo(requestJson)` unchanged.

The per-item status vocabulary is exactly:

```text
success
invalid_guid
not_found
ambiguous_name
projection_failure
instantiation_failure
```

The non-success `error` vocabulary is exactly:

```text
invalid_guid
component_not_found
proxy_projection_failed
provenance_projection_failed
component_instantiation_failed
implementation_projection_failed
```

- [x] **Step 1: Write RED request, resolution, and correlation tests**

Add tests proving:

```text
Both_or_neither_selector_families_refuse
Empty_array_nonarray_and_nonstring_refuse
Names_preserve_order_case_and_duplicates
Guids_preserve_selector_and_emit_canonical_guid
Invalid_guid_is_per_item_and_does_not_abort_later_items
Unknown_kind_is_per_item_proxy_projection_failure
Names_use_one_complete_eligible_exact_name_scan
Unique_name_and_guid_share_success_shape
Missing_name_and_guid_are_correlated_not_found
Ambiguous_name_returns_every_candidate_without_instantiation
Mixed_success_missing_ambiguous_and_failure_batch_continues
All_item_failures_still_complete_the_batch
```

Instrument the fake server so `ObjectProxies` is read exactly once for the batch. Make
unexpected `FindObjects` and knowledge access impossible in these tests.

- [x] **Step 2: Write RED provenance and implementation tests**

Add compiled fakes for `FindAssembly(Guid)` and user-object fakes created from an injected
path factory. Cover exact successful shapes and each failure prefix:

```text
Compiled_provenance_uses_selected_proxy_library_guid
Compiled_missing_assembly_retains_proxy_and_fails_provenance
User_object_provenance_uses_path_and_exact_data_hash
User_object_path_mismatch_or_normalization_failure_fails_provenance
User_object_null_data_returns_paired_nulls
User_object_unexpected_data_or_hash_error_fails_provenance
Instantiation_failure_retains_complete_provenance
Implementation_uses_exact_host_property_sources
Implementation_failure_retains_provenance_and_omits_implementation_and_params
Params_object_is_unchanged
Params_null_is_success_including_existing_caught_exception
Failure_prefixes_accumulate_monotonically
```

The implementation-source fake must make `Type.Name` and `AssemblyQualifiedName` visibly
different from `Type.FullName` so the regression detects substitution.

- [x] **Step 3: Prove RED**

Run the same focused managed test command from Task 1. Expected failures: managed endpoint
still accepts GUIDs only, selects through a GUID map, replaces proxy names from the
instance, and lacks provenance/implementation/outcome fields.

- [x] **Step 4: Parse one closed selector family in the managed endpoint**

Deserialize without coercion. Admission is:

```csharp
bool hasNames = root.TryGetProperty("names", out var namesElement);
bool hasGuids = root.TryGetProperty("guids", out var guidsElement);
if (hasNames == hasGuids) return Failure(...);
```

Require a nonempty array and `JsonValueKind.String` for every item. Preserve each exact
decoded string in a selector record:

```csharp
new { Kind = "name", Value = exactValue }
new { Kind = "guid", Value = exactValue }
```

Do not trim, case-fold, deduplicate, or discard invalid GUID selectors.

- [x] **Step 5: Resolve from one live proxy view**

Snapshot `ObjectProxies` once. Project proxy identity/source kind with the same strict
Task 1 helper. Resolve:

```text
name -> complete eligible case-insensitive Desc.Name equality
guid -> direct canonical GUID match without ordinary eligibility filtering
```

For each selector, append one item before moving to the next. Ambiguity returns every
complete candidate in `CompareProxies` then GUID order and makes zero provenance,
instantiation, or Params calls for that selector.

- [x] **Step 6: Implement closed compiled and user-object provenance**

Compiled:

```text
selected proxy LibraryGuid
-> server.FindAssembly(LibraryGuid)
-> libraryGuid, libraryName, libraryVersion,
   assemblyFullName, assemblyVersion, assemblyLocation
```

Not-found assembly or any required projection failure emits
`projection_failure/provenance_projection_failed` with selector, canonical GUID, proxy
identity, and sourceKind retained.

User object:

```text
selected proxy Location
-> construct GH_UserObject(string path)
-> retain exact GH_UserObject.Path as provenance.path
-> normalize proxy Location and GH_UserObject.Path independently with Path.GetFullPath
-> replace Path.AltDirectorySeparatorChar with Path.DirectorySeparatorChar
-> require StringComparison.OrdinalIgnoreCase equality
-> project BaseGuid for later implementation
-> Data null => paired null content fields
-> Data byte[] => exact LongLength and uppercase SHA-256
```

The returned `provenance.path` remains the exact unnormalized `GH_UserObject.Path` string.
Do not resolve symlinks, infer package identity, or return the normalized comparison
values. Mismatch, path normalization, construction, path runtime-type, byte conversion,
or hashing failure emits the same provenance failure prefix. Use
`System.Security.Cryptography.SHA256` already in the BCL and never serialize or log raw
bytes.

The optional `userObjectFactory` exists only on the internal same-module helper and is
used by tests; the public path supplies the exact reflected `GH_UserObject(string)`
constructor. Do not add a service, interface, or registry for this seam.

- [x] **Step 7: Instantiate the selected proxy and project implementation exactly**

Call the exact selected proxy's `CreateInstance()` once. Do not call
`CreateComponentFromGuid()` and do not rescan proxies.

Project:

```csharp
var type = component.GetType();
var assembly = type.Assembly;
var assemblyName = assembly.GetName();
var baseGuidValue = sourceKind == "user_object"
    ? ghUserObject!.GetType().GetProperty("BaseGuid")?.GetValue(ghUserObject)
    : null;
var componentGuidValue = type.GetProperty("ComponentGuid")?.GetValue(component);

// Strictly validate/project these values into the closed implementation DTO:
// baseGuid                <- baseGuidValue, or code-owned null for compiled
// componentGuid           <- componentGuidValue
// runtimeType             <- type.FullName
// runtimeAssemblyName     <- assemblyName.Name
// runtimeAssemblyVersion  <- assemblyName.Version?.ToString()
// runtimeAssemblyLocation <- assembly.Location
```

Treat only the three runtime-assembly values as host-nullable. Compiled `baseGuid` is the
one separate code-owned null. Any other missing/unreadable/unexpected value emits
`projection_failure/implementation_projection_failed`, retains completed provenance, and
omits implementation and Params.

- [x] **Step 8: Call `GetComponentParams()` without changing it**

Use its current return value directly:

```csharp
var paramsInfo = GetComponentParams(component);
```

An object becomes the existing `params` shape. Null—including an exception caught inside
`GetComponentParams()`—is successful `params: null`. Do not add another status or catch
around it that changes current behavior.

- [x] **Step 9: Close batch equations and bridge custody**

Return internal `Success=true` after every admitted selector has one valid ordered item:

```csharp
Data = new
{
    Count = results.Count,
    Errors = results.Count(item => item.Status != "success"),
    Results = results
};
```

Malformed request, component-server failure, or target-wide reflection failure remains
top-level `Success=false`. Do not change `NativeGhBridgeRegistrar.HandleBatchComponentInfo`.

Add a source-bound bridge regression asserting the callback still passes `requestJson`
directly to `Handler.HandleBatchComponentInfo(requestJson)` with no parse/re-encode step.

- [x] **Step 10: Run GREEN and compile the full managed project**

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore `
  --filter "FullyQualifiedName~GrasshopperComponentDiscoveryContractTests|FullyQualifiedName~NativeGhBridgeRegistrarTests" `
  --verbosity minimal
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --verbosity minimal
```

Record exact passing/failing counts, warning count, production growth, and any established
unrelated failures. Stop on a new failure.

- [x] **Step 11: Commit Task 2**

```powershell
git add src/Rook/Handlers/GrasshopperHandler.cs `
  src/Rook.Tests/Handlers/GrasshopperComponentDiscoveryContractTests.cs `
  src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs `
  docs/superpowers/plans/2026-08-09-grasshopper-component-discovery-coherence.md
git commit -m "feat: preserve Grasshopper component metadata identity"
```

Observed Task 2 evidence on 2026-08-10: the new reflection seam failed all `18`
metadata test cases before production because `HandleBatchComponentInfoFromServer` did
not exist. After the managed implementation, exact-shape assertions, user-object path
and content failures, and the unchanged bridge-forwarding regression were restored, the
focused managed seam passed `101/101`. The complete managed suite passed `3713/3713`.
A no-incremental managed build completed with exit `0`; its `450` emitted warning lines
are established repository warnings and none points to the Task 2 handler region or the
new/changed Task 2 tests. Task 2 production growth is `389 additions` and `100 deletions`
in the existing managed owner. The bridge production callback and existing
`GetComponentParams()` implementation remain byte-unchanged.

Task 2 review repair on 2026-08-10 moved `.ghuser` `BaseGuid` projection into the
implementation phase and replaced the eager batch-wide GUID index with selector-local
reads over the one frozen proxy snapshot. The four initial regressions failed before the
repair: throwing, null, and wrong-type `BaseGuid` values were misclassified as provenance
failures, while one malformed proxy erased the mixed batch. After repair, valid path/hash
provenance survives all three implementation failures; conclusive selectors before and
after a malformed proxy survive; incomplete GUID scans cannot guess `not_found`; and
obsolete proxies do not trigger an unnecessary exposure read. The incomplete-scan guard
was mutation-checked: removing it made its causal regression fail `1/1`. The repaired
focused seam passes `107/107`, and the complete managed suite passes `3719/3719`.
The repair delta is `91 additions` and `34 deletions`; cumulative Task 2 production
growth from the approved Task 1 head is `445 additions` and `99 deletions`, still wholly
inside the existing managed owner.

**Mandatory review gate:** stop. Review the complete selector-to-proxy-to-provenance-to-
implementation-to-Params chain, every failure prefix, one-view/one-instantiation counts,
bridge custody, and no change to `GetComponentParams()` before Task 3.

---

### Task 3: One-call Python ownership and public correlation

**Files:**
- Modify: `mcp_server/src/rook/server.py:8465-8481,10360-10390,15107-15118,18021-18075`
- Create: `mcp_server/tests/test_grasshopper_component_discovery_coherence.py`
- Modify: `mcp_server/tests/test_server_component_deprecation.py:110-240`

**Interfaces:**
- Consumes: one managed response with exact ordered selector evidence.
- Produces: `_validate_gh_batch_component_info_arguments(arguments: dict) -> tuple[str, list[str], dict]` and `_project_gh_batch_component_info_result(selector_kind: str, selectors: list[str], result: dict) -> dict` inside `server.py`.
- Preserves: existing `_project_tool_result` behavior for internal and public MCP callers.

- [ ] **Step 1: Repair the stale no-contact fixture and replace obsolete metadata tests**

In `test_server_component_deprecation.py`, make `patched_server` supply a non-Rhino test
policy before public `call_tool()` enters target selection:

```python
monkeypatch.setattr(
    server.targeting,
    "policy_for_tool",
    lambda _name: server.targeting.RhinoToolPolicy(False, "read"),
)
```

Keep both `gh_edit` assertions unchanged. Replace the two metadata tests that expect
`UnifiedStore`/library resolution with one-call managed ownership assertions.

- [ ] **Step 2: Write RED Python admission and schema tests**

Assert the advertised schema exposes both `names` and `guids`, describes exactly one
family, and preserves no copied catalog. Test refusal before `call_rhino` for:

```text
both families
neither family
empty selected family
non-list family
non-string element
```

Do not require JSON-Schema `oneOf`; local admission is authoritative and avoids reopening
provider-schema compatibility. The schema descriptions must still state the rule.

- [ ] **Step 3: Write RED one-call and correlation tests**

Use `AsyncMock` for `call_rhino` and hostile mocks for `get_unified_store` and any library
route. Prove:

```python
await server.call_tool("gh_batch_component_info", {"names": ["Area", "Area"]})
```

causes exactly:

```text
one POST /gh/batch-component-info
payload == {"names": ["Area", "Area"]}
zero UnifiedStore calls
zero /gh/library calls
```

Repeat for GUIDs. Add returned-response cases for success, not-found, ambiguity, invalid
GUID, projection failure, instantiation failure, mixed outcomes, all failures, and
target-wide failure.

- [ ] **Step 4: Implement strict local selector-family validation**

Use exact built-in JSON carrier types:

```python
def _validate_gh_batch_component_info_arguments(arguments: dict):
    has_names = "names" in arguments
    has_guids = "guids" in arguments
    if has_names == has_guids:
        raise ValueError("exactly one of names or guids is required")
    kind = "name" if has_names else "guid"
    key = "names" if has_names else "guids"
    values = arguments[key]
    if type(values) is not list or not values:
        raise ValueError(f"{key} must be a nonempty array")
    if any(type(value) is not str for value in values):
        raise ValueError(f"{key} items must be strings")
    return kind, list(values), {key: list(values)}
```

Convert validation errors into the existing internal failure envelope before target
contact; do not surface Python exception text through a new taxonomy.

- [ ] **Step 5: Forward once and validate host correlation**

Replace the current `UnifiedStore` and `/gh/library` loops with:

```python
selector_kind, selectors, body = _validate_gh_batch_component_info_arguments(arguments)
host_result = await call_rhino(
    "/gh/batch-component-info", "POST", body, port=port
)
result = _project_gh_batch_component_info_result(
    selector_kind, selectors, host_result
)
```

The projector must require a successful host envelope to contain a dict with integer
`count`, integer `errors`, and list `results`; require lengths and error counts to match;
require each `selector.kind/value` to equal the corresponding admitted selector exactly;
and require only the closed status/error shapes. Any mismatch returns top-level failure.

- [ ] **Step 6: Add names-only compatibility summaries**

For `selector_kind == "name"` only:

```python
resolved = {
    item["selector"]["value"]: item["guid"]
    for item in results
    if item["status"] == "success"
}
unresolved = [
    item["selector"]["value"]
    for item in results
    if item["status"] != "success"
]
```

Insert those fields alongside the managed `count/errors/results`. The ordered results
array remains authoritative when repeated successful names collapse in `resolved`.
GUID requests omit both fields.

- [ ] **Step 7: Close `gh_library` empty-string transport semantics**

In the canonical MCP branch, use key presence plus nonempty string rather than generic
rewriting:

```python
if "search" in arguments and arguments["search"] != "":
    params["search"] = arguments["search"]
if "category" in arguments and arguments["category"] != "":
    params["category"] = arguments["category"]
if "exact" in arguments:
    params["exact"] = arguments["exact"]
```

Whitespace-only strings pass unchanged. Omitted and empty strings both omit the query
parameter. Do not trim.

- [ ] **Step 8: Prove direct and contained MCP semantics**

Call the internal path and the registered public handler, then call the same targets
through `rook_tools_call`. Prove:

```text
complete mixed/all-failure batch -> internal success true, public isError false
top-level malformed/target/host failure -> public isError true
structuredContent describes the target directly
legacy TextContent remains owned by the existing projection
no gateway double wrapping
```

- [ ] **Step 9: Run GREEN and the focused Python seam**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_grasshopper_component_discovery_coherence.py `
  mcp_server/tests/test_server_component_deprecation.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py -q
```

Expected: every selected test passes. Report exact count and warnings.

- [ ] **Step 10: Run source-surface scans**

Use an AST/source test in the new test module to isolate the
`gh_batch_component_info` case and assert it contains none of:

```text
get_unified_store
resolve_active_component_guid_by_name
/gh/library
```

Also assert exactly one `/gh/batch-component-info` call expression appears.

- [ ] **Step 11: Commit Task 3**

```powershell
git add mcp_server/src/rook/server.py `
  mcp_server/tests/test_grasshopper_component_discovery_coherence.py `
  mcp_server/tests/test_server_component_deprecation.py `
  docs/superpowers/plans/2026-08-09-grasshopper-component-discovery-coherence.md
git commit -m "feat: delegate component selectors to Grasshopper"
```

**Mandatory review gate:** stop. Review must verify zero pre-contact calls on invalid
input, exactly one target call for admitted input, exact correlation, names-only summary
compatibility, all-failure MCP success, and zero knowledge/library identity work in
Python before Task 4.

---

### Task 4: Dispatcher parity, knowledge exclusion, and full no-contact vertical

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py:858-866`
- Modify: `mcp_server/src/rook/learning/knowledge_injector.py:78-89`
- Modify: `mcp_server/tests/test_grasshopper_component_discovery_coherence.py`
- Modify: `mcp_server/tests/test_knowledge_injector.py`

**Interfaces:**
- Consumes: existing direct ToolDispatcher transformation and universal knowledge gate.
- Produces: exact direct/canonical `gh_library` parity and deterministic no-injection for both authoritative tools.

- [ ] **Step 1: Write RED direct-dispatch parity tests**

Parameterize:

```python
({}, {})
({"search": ""}, {})
({"search": "   "}, {"search": "   "})
({"category": ""}, {})
({"category": "   "}, {"category": "   "})
({"exact": False}, {"exact": False})
({"exact": True}, {"exact": True})
```

Assert `_transform_gh_library` returns `("/gh/library", "GET", expected)` and does not
mutate the caller dictionary.

- [ ] **Step 2: Implement the minimal dispatcher correction**

```python
def _transform_gh_library(args: dict) -> Tuple[str, str, dict]:
    params = {}
    if "search" in args and args["search"] != "":
        params["search"] = args["search"]
    if "category" in args and args["category"] != "":
        params["category"] = args["category"]
    if args.get("limit"):
        params["limit"] = args["limit"]
    if "exact" in args:
        params["exact"] = args["exact"]
    return "/gh/library", "GET", params
```

Do not change another transform or add a generic query normalizer.

- [ ] **Step 3: Write RED authoritative-tool knowledge tests**

Add exact assertions:

```python
assert "gh_library" in _SKIP_TOOLS
assert "gh_batch_component_info" in _SKIP_TOOLS
assert should_inject("gh_library", success_dict) is False
assert should_inject("gh_batch_component_info", success_dict) is False
```

Prove the ordinary result cannot reach injection: `should_inject()` must return false,
and a real server-dispatch regression with `inject_knowledge` patched to raise must still
return the ordinary tool result for both names.

- [ ] **Step 4: Add the two tools to the existing skip set**

Only edit `_SKIP_TOOLS`:

```python
"gh_library",
"gh_batch_component_info",
```

Do not redesign mapping categories or fix the two known mapping failures.

- [ ] **Step 5: Add one causal full vertical**

The Python vertical must use the real server dispatch and fake only the native transport.
Run:

```text
rook_tools_call(gh_library exact search)
-> one fake /gh/library call
-> ranked compact candidate result
-> zero knowledge calls

rook_tools_call(gh_batch_component_info names with duplicate)
-> one fake POST /gh/batch-component-info
-> exact managed selector outcomes
-> Python correlation and compatibility summaries
-> public structured result
-> zero knowledge calls
```

Assert the complete call ledger, exact arguments, exact returned fields, no copied
provenance in search, no double wrapping, and no second target call.

- [ ] **Step 6: Run the focused seam and preserve known failures**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_grasshopper_component_discovery_coherence.py `
  mcp_server/tests/test_server_component_deprecation.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_dispatcher_safety.py -q

& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_knowledge_injector.py -q
```

Expected: first command fully green. Second command has exactly the two documented
`TestGHOperationMapping` failures and no others. Record exact counts and warnings.

- [ ] **Step 7: Compile Python and run managed/Python adjacent seams**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m compileall -q `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/src/rook/learning/knowledge_injector.py `
  mcp_server/tests/test_grasshopper_component_discovery_coherence.py

dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --verbosity minimal
git diff --check
```

Stop on a new failure or a changed known-failure signature.

- [ ] **Step 8: Report growth and audit scope**

```powershell
git diff --numstat 411613d7 -- `
  src/Rook/Handlers/GrasshopperHandler.cs `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/src/rook/learning/knowledge_injector.py
git diff --name-only 411613d7
```

Confirm there are exactly four production owners, no new production module, and no
changes to `gh_edit`, `gh_snapshot`, T*/C*, receipt code, or public MCP projection.

- [ ] **Step 9: Commit Task 4**

```powershell
git add mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/src/rook/learning/knowledge_injector.py `
  mcp_server/tests/test_grasshopper_component_discovery_coherence.py `
  mcp_server/tests/test_knowledge_injector.py `
  docs/superpowers/plans/2026-08-09-grasshopper-component-discovery-coherence.md
git commit -m "fix: align component discovery boundaries"
```

**Mandatory review gate:** stop. Independent review must approve direct/canonical parity,
knowledge exclusion, public/gateway result semantics, production growth, and exact scope
before final reconciliation.

---

### Task 5: Architecture reconciliation and final verification

**Files:**
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Modify: `docs/superpowers/plans/2026-08-09-grasshopper-component-discovery-coherence.md`

**Interfaces:**
- Consumes: approved Tasks 1-4.
- Produces: durable architecture wording and a reproducible verification ledger only.

- [ ] **Step 1: Add the concise architecture statement**

Record:

```text
Grasshopper native FindObjects proposes ordinary candidates.
Proxy GUID and sourceKind own component-type identity.
The managed Grasshopper endpoint resolves one names-or-GUID batch against one live view.
Compiled and user-object provenance remain distinct.
Python forwards once, verifies correlation, and adds compatibility summaries.
Knowledge does not alter authoritative discovery or metadata.
Existing T*/C* identities own graph execution after type selection.
```

Do not copy the full specification or qualification reports into the architecture note.

- [ ] **Step 2: Run the complete prescribed verification seam**

Run all Task 4 commands plus:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --verbosity minimal
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_grasshopper_component_discovery_coherence.py `
  mcp_server/tests/test_server_component_deprecation.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_dispatcher_safety.py -q
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_knowledge_injector.py -q
```

Report exact managed and Python pass/fail/warning counts. The only accepted Python
failures are the two exact documented knowledge-mapping identities.

- [ ] **Step 3: Run final source-surface and repository checks**

```powershell
$protectedDelta = git diff --unified=0 411613d7 -- `
  src/Rook/Handlers/GrasshopperHandler.cs `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/src/rook/learning/knowledge_injector.py |
  rg -i -P '^(?!\+\+\+|---)[+-].*(gh_edit|gh_snapshot|T\*|C\*|receipt)'
if ($LASTEXITCODE -eq 0) {
  throw "Protected execution/identity surface changed:`n$protectedDelta"
}
if ($LASTEXITCODE -ne 1) { exit $LASTEXITCODE }

$allowed = @(
  'src/Rook/Handlers/GrasshopperHandler.cs',
  'mcp_server/src/rook/server.py',
  'mcp_server/src/rook/agent/tool_dispatcher.py',
  'mcp_server/src/rook/learning/knowledge_injector.py',
  'src/Rook.Tests/Handlers/GrasshopperComponentDiscoveryContractTests.cs',
  'src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs',
  'mcp_server/tests/test_grasshopper_component_discovery_coherence.py',
  'mcp_server/tests/test_server_component_deprecation.py',
  'mcp_server/tests/test_knowledge_injector.py',
  'docs/CURRENT_ARCHITECTURE.md',
  'docs/superpowers/specs/2026-08-08-grasshopper-component-discovery-coherence-design.md',
  'docs/superpowers/plans/2026-08-09-grasshopper-component-discovery-coherence.md'
)
$changed = @(git diff --name-only 411613d7)
$unexpected = @($changed | Where-Object { $_ -cnotin $allowed })
if ($unexpected.Count -ne 0) {
  throw "Unexpected changed path(s): $($unexpected -join ', ')"
}

git diff --check
git status --short --branch
git diff --name-only 411613d7
```

The AST-isolated Python regression from Task 3 is the authoritative proof that the
metadata branch owns no knowledge or `/gh/library` fallback. Do not replace it with a
raw grep: the production server and its causal test intentionally contain those terms.
The zero-context diff scan above proves this slice did not add lines to protected
execution/identity surfaces.

- [ ] **Step 4: Reconcile the ledger**

Mark only observed steps complete. Record:

```text
exact files changed
exact production additions/deletions per owner
exact test counts and known failure signatures
managed compilation result
Python compilation result
source-surface scan result
git diff --check result
worktree status
confirmation of zero live/model contact
```

- [ ] **Step 5: Commit documentation only**

```powershell
git add docs/CURRENT_ARCHITECTURE.md `
  docs/superpowers/plans/2026-08-09-grasshopper-component-discovery-coherence.md
git commit -m "docs: reconcile component discovery architecture"
```

Stop for independent final review. Do not deploy, contact Rhino/Grasshopper, run the Opus
control, run a local-model comparison, push, or open a PR without separate authorization.
