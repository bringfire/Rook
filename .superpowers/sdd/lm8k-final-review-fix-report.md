# LM8K Final-Review Repair Report

## Status

PASS. All seven final-review findings are repaired in one integration patch. The managed fence, native callback forwarding, Python dispatch, targeting policy, smoke receipt semantics, baseline setup evidence, and exact provenance checks have deterministic regression coverage.

No Rhino or Grasshopper live invocation was run. The post-merge smoke script was tested only with fake executors matching the real `_call_tool_dispatch` `{success, data}` envelope.

## Repair Summary

1. `NativeGhBridgeRegistrar.HandleInspectOutput` now forwards `readiness_receipt_id` to `GrasshopperHandler.InspectOutput`.
2. `gh_solve_readiness` and `gh_wait_for_solve_readiness` are explicit Rhino read tools in targeting policy. The already-exposed `gh_connect` tool was also added to the known-tool set as a mutator so the pre-existing public surface remains classified.
3. Smoke fakes and consumers now use the real dispatcher envelope, including `rhino_ping`, `gh_library`, wait status, mutation receipt, and inspect data nesting.
4. Pending-to-ready validation keeps receipt ID, document session, and mutation epoch immutable while requiring `solution_run_epoch` to advance beyond the prior completed epoch and bind exactly to `completed_solution_run_epoch`.
5. Managed fenced reads reject explicit empty or whitespace receipt IDs with `readiness_receipt_id_invalid` before output extraction. Python forwards explicitly supplied blank values instead of dropping them. Omission remains the legacy unfenced path.
6. Fixture setup now performs a setup-only receipted `gh_set_value` on the offset slider and waits for its correlated ready receipt before the evidence mutation. The ready setup receipt is recorded separately in `baseline_setup_summary.json`. No output polling or sleep was added.
7. Fenced output provenance now matches both `solution_run_epoch` and `completed_solution_run_epoch` to the ready receipt.

## Surface Count

The review requested changing the historical `443` pins to `445` for the two LM8K tools. On this branch, `gh_connect` had already been exposed by commit `0c3161b9` without updating those pins, so the executable surface before LM8K was already one above the historical pin. Preserving that unrelated public tool gives the accurate branch arithmetic:

```text
historical pinned surface 443
+ pre-existing gh_connect   1
+ LM8K readiness tools      2
= current surface         446
```

The surface tests therefore pin `446` and explicitly require both readiness tools. Removing `gh_connect` to force `445` would revert unrelated public work.

## RED Evidence

### Existing targeting and surface failures

Command:

```powershell
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_multi_instance_targeting.py::test_every_exposed_tool_has_policy_entry mcp_server\tests\test_server_tool_profiles.py::test_full_surface_is_443_and_gates_deprecated mcp_server\tests\test_server_tool_profiles.py::test_all_live_tools_is_unprofiled_443 mcp_server\tests\test_server_tool_profiles.py::test_readonly_partition_over_live_surface -q
```

Result: **4 failed**. Targeting lacked `gh_solve_readiness`, `gh_wait_for_solve_readiness`, and the pre-existing `gh_connect`; surface assertions expected 443 while the branch exposed 446.

### Managed callback and fail-closed fence regressions

Command:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~InspectOutputCallback_ForwardsOptionalReadinessReceipt|FullyQualifiedName~FencedInspect_ExplicitBlankReceiptFailsClosedBeforeExtraction|FullyQualifiedName~InspectOutput_OmittedReceiptPreservesLegacyUnfencedRead"
```

Result: **3 failed, 1 passed**. Callback source omitted the receipt argument; empty and whitespace receipts performed successful legacy reads; omission compatibility already passed.

### Python forwarding and smoke semantics regressions

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'mcp_server\src'); & 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_gh_solve_readiness_tools.py::test_inspect_output_forwards_explicit_blank_receipt_for_managed_rejection mcp_server\tests\test_multi_instance_targeting.py::test_solve_readiness_tools_are_explicit_rhino_reads mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_consumes_real_dispatch_envelopes mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_accepts_correlated_ready_epoch_advance mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_establishes_and_records_setup_readiness_before_claim_mutation mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_rejects_mismatched_solution_run_provenance -q
```

Result: **6 failed, 1 passed**. Empty receipt forwarding, policy classification, real envelopes, legal epoch advancement, setup readiness, and solution-run provenance each failed for the reported reason. Whitespace forwarding already passed because it was truthy, confirming the empty-string-specific Python fallback.

### Immutable identity presence regression

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'mcp_server\src'); & 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_rejects_ready_transition_missing_immutable_identity -q
```

Result: **2 failed**. Missing session and mutation fields were rejected only later as output provenance mismatches instead of at the pending-to-ready gate.

## GREEN Evidence

### Focused managed repair checks

Command:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~InspectOutputCallback_ForwardsOptionalReadinessReceipt|FullyQualifiedName~FencedInspect_ExplicitBlankReceiptFailsClosedBeforeExtraction|FullyQualifiedName~InspectOutput_OmittedReceiptPreservesLegacyUnfencedRead"
```

Result: **4 passed**.

### Focused Python repair checks

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'mcp_server\src'); & 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_gh_solve_readiness_tools.py::test_inspect_output_forwards_explicit_blank_receipt_for_managed_rejection mcp_server\tests\test_multi_instance_targeting.py::test_solve_readiness_tools_are_explicit_rhino_reads mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_consumes_real_dispatch_envelopes mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_accepts_correlated_ready_epoch_advance mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_establishes_and_records_setup_readiness_before_claim_mutation mcp_server\tests\test_gh_solve_readiness_live_smoke.py::test_smoke_rejects_mismatched_solution_run_provenance -q
```

Result: **7 passed**.

### Targeting and surface integration

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'mcp_server\src'); & 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_gh_solve_readiness_tools.py mcp_server\tests\test_gh_solve_readiness_live_smoke.py mcp_server\tests\test_server_tool_profiles.py mcp_server\tests\test_multi_instance_targeting.py mcp_server\tests\test_server_gh_knowledge_wrappers.py -q
```

Result: **113 passed**.

### Managed readiness and bridge suite

Command:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~GhSolutionLifecycleAdapterTests|FullyQualifiedName~GhSolveReceiptRegistryTests|FullyQualifiedName~GrasshopperHandlerReadinessTests|FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~GrasshopperDocumentLifecycleSourceTests|FullyQualifiedName~RequestPostMutationSolveTests|FullyQualifiedName~GhSolveReadinessCoordinatorTests"
```

Result: **130 passed**.

### Python readiness, surface, targeting, and probe-drift suite

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'mcp_server\src'); & 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_gh_solve_readiness_tools.py mcp_server\tests\test_server_gh_knowledge_wrappers.py mcp_server\tests\test_gh_solve_readiness_live_smoke.py mcp_server\tests\test_server_tool_profiles.py mcp_server\tests\test_multi_instance_targeting.py mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
```

Result: **231 passed**. LM8F/I/J files were not modified.

### Python compile checks

Command:

```powershell
$env:PYTHONPATH=(Resolve-Path 'mcp_server\src'); & 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m py_compile mcp_server\tools\gh_solve_readiness_live_smoke.py mcp_server\src\rook\server.py mcp_server\src\rook\targeting.py
```

Result: **exit 0**.

### Native ABI and plugin build

Command:

```powershell
.\build_native.ps1 -Configuration Debug -VCToolsVersion 14.44.35207
```

Result: **exit 0**. `GrasshopperBridgeAbiValidationTests.cpp` compiled and printed `Grasshopper bridge ABI validation tests passed.` before `RookNative.vcxproj` built `src\RookNative\bin\Debug\x64\RookNative.rhp`.

### Diff hygiene

Command:

```powershell
git diff --check
```

Result: **exit 0**; only line-ending conversion notices were emitted by Git.

## Scope

The patch modifies only the managed handler/bridge and tests, Python server/targeting/smoke and tests, this report, and no planner, worker, LM8F/I/J probe, project, or live-run artifact. Existing dirty changes in `knowledge/gh/notes/teaching_4f2b9009.json` and `knowledge/gh/operations_knowledge.json` were left untouched and excluded from the commit.
