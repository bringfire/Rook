# RookChat Prime Runtime Topology Gate 7A V5 Correction

**Status:** OFFLINE CORRECTION COMPLETE; GATE 7B V5 NOT AUTHORIZED

## Disposition

The original Gate 7A V5 report is preserved as a blocked package. Independent
review found two remaining custody defects:

1. recoverable mode could reclaim an authoritative lifetime lock when
   `owner.json` was missing, malformed, partial, or unknown; and
2. executable/package custody was verified during harness configuration but not
   again before each contender or reopen launch.

This correction closes only those boundaries and removes the discarded Windows
process-surveillance design from the active plan. It introduces no V6 topology,
daemon redesign, supervisor, retry, process monitor, or new recovery mechanism.
Gate 7B was not launched.

## Unknown-Lock Refusal

The lease directory remains the authority. Recoverable mode now follows one
closed decision:

```text
valid version-3 lifetime owner
-> refuse session_already_active

valid version-1 recoverable owner proven alive
-> refuse session_already_active

valid version-1 recoverable owner proven dead
-> permit recoverable reclamation

missing, malformed, partial, legacy, or unknown owner metadata
-> refuse session_already_active
```

Only the third case reaches `reclaimRecoverableLease()`. The refusal path never
removes or rewrites the unknown lock directory. This preserves daemon recovery
for valid dead version-1 owners without weakening lifetime authority during the
directory-created/metadata-unpublished interval.

The new parameterized regression first failed for all four unknown-owner shapes
because each was reclaimed. It passes after the narrowed admission check.

## Per-Launch Custody

`_launch()` now owns one complete launch transaction:

```text
construct exact argv and direct child owner
-> verify Node path/hash
-> verify complete Prime dist manifest and cli.js entry
-> verify uv.exe path/hash
-> verify staged goal package manifest
-> verify staged rook-full package manifest
-> Popen exactly once
```

The direct vertical, first owner, contender, and reopen all use this same path.
No caller may create an `OwnedPrimeProcess` through the harness and start it
later under stale custody.

The causal regression changes `dist/bundle/cli.js` when the first owner closes.
The contender has already been refused. Reopen then fails bundle verification,
and the fake process record proves generation 3 was never started.

## Plan Reconciliation

The active plan and topology amendments now state the implemented boundary:

- Task 7 continues only in the recovery worktrees; old review worktrees remain
  quarantine evidence;
- supported production launch sites set the internal policy contract:
  in-process RPC uses lifetime, daemon and owned-worker paths use recoverable;
- that environment field is convention-scoped, not topology-authenticated;
- process ownership is one hidden direct handle with transactional startup;
- normal settlement is RPC/EOF plus graceful exit zero;
- handle-local terminate/kill is gate-failing safety cleanup; and
- PowerShell identity probes, Toolhelp snapshots, `taskkill`, PID-tree
  authority, process polling, and process-name cleanup are not admitted.

The plan records Tasks 0-6 as historical, Task 7 Steps 0-3 as implemented, and
Gate 7A review as the current stop. Gate 7B remains unchecked and unauthorized.

## Custody

```text
Prime commit
779d5ffbfa3e623b91e00571c274172a684ec9db

Prime tree
d869470f8fcd98fe3bbebd22445d9274bbedad21

Rook V5 correction implementation commit
64333f40629c41ae8a74cf97b390823101bccd20

Rook implementation tree
7e721a2666852659559f4339f9d1143b8a8d0187

Prime bundle manifest identity
013B622DF0B48C4CA708E7F82EFEC2825EE4B320A2021A848E426D6277F0FEDF

Prime bundle manifest file SHA-256
4B32D8E917E1F67602B422FBDD8D1A35E3502FD536E17884E931853795614507

Harness SHA-256
FD2DB5B22CADBDE03BF840C66767E8CE59FA6538008B4BBC7E4DF546B2B9F188

Wrapper SHA-256
883B279994D2ACD6FE6712E6F3C83CDF483C91D099BD969C090DD553B2E7A45A

Slices 3-4 plan SHA-256
0E20DBF65260AE866087927A0BA34FE9FB6FC9D2E8B93FDA7BB4095D705B1FC4

Runtime-topology amendment SHA-256
338D035EDD963912FCF1CB4B862E94540AF450E7D638E14E6FED54C29ED8B3C4

Task 7 recovery amendment SHA-256
3117928FC758CE21BEF7BE95D4DBC456F35A4E69149014259C92E78625DCB9A9

Prime goal package manifest
D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7

Rook package manifest
2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678

Prime package-lock.json
C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D

Rook uv.lock
7BF31108A2CA69B65D9DE2936CFD7022A7E4BBE2574C3E512CBBD159B7ADE171
```

The corrected manifest is separate from the blocked V5 manifest and binds the
clean Prime commit above. The V2-V5 Gate 7B evidence roots remain absent.

## Offline Verification

RED:

```text
Prime unknown-lock regression: 4 failed, 14 passed
Rook per-launch bundle-drift regression: 1 failed, 19 passed
```

GREEN:

```text
Prime focused lease and compatibility tests: 80 passed
Prime repository-wide source and test TypeScript check: passed
Prime local package build and coding-agent bundle: passed
Rook runtime contract, product adapter, harness, and wrapper: 85 passed
Harness and wrapper Python compilation: passed
Corrected Prime bundle replay: 86/86 entries
```

One excluded build attempt used the repository root build, whose model-catalog
generator fetched current public catalog data and changed
`packages/ai/src/models.generated.ts`. Those generated bytes were not admitted:
the file was restored exactly to the committed blob, clean status was verified,
and the final AI, agent, and coding-agent outputs were rebuilt locally without
catalog generation before the corrected manifest was frozen. The later root
`npm run bundle` subcommand also failed because no root-level bundle script
exists; the package-local coding-agent build already owns bundling.

No Prime CLI, daemon, kernel, provider inference, model session, Rhino,
Grasshopper, MCP, deployment, Gate 7B transaction, or process cleanup action was
launched by this correction.

## Review Stop

Independent review must authenticate the wrapper before Python executes it and
supply the exact final clean Rook commit:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server

$python = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/mcp_server/.venv/Scripts/python.exe'
$wrapper = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/run_rookchat_prime_runtime_topology_gate_7b.py'
$expectedWrapper = '883B279994D2ACD6FE6712E6F3C83CDF483C91D099BD969C090DD553B2E7A45A'

if ((Get-FileHash -LiteralPath $wrapper -Algorithm SHA256).Hash -ne $expectedWrapper) {
    throw 'Gate 7B V5 wrapper differs from the reviewed correction.'
}

& $python $wrapper `
    --approved-rook-commit '<INDEPENDENT-REVIEW-SUPPLIED-EXACT-COMMIT>' `
    --approved-harness-sha256 'FD2DB5B22CADBDE03BF840C66767E8CE59FA6538008B4BBC7E4DF546B2B9F188'

if ($LASTEXITCODE -ne 0) {
    throw "Gate 7B V5 failed with exit code $LASTEXITCODE. Do not retry."
}
```

Gate 7B V5 requires separate independent authorization.
