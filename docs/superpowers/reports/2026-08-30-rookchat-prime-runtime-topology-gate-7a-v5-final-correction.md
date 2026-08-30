# RookChat Prime Runtime Topology Gate 7A V5 Final Correction

Status: OFFLINE CORRECTION COMPLETE; GATE 7B NOT EXECUTED OR AUTHORIZED

Date: 2026-08-30

## Scope

This pass closes the final reviewed Gate 7A V5 findings without changing the
direct in-process product topology or restoring process surveillance.

Prime commit:

```text
46dbf2749d64446820fbf31e52d8766e5ee87be9
tree 3e3f065683550f6ea90d474d266087230f55b9c7
```

Rook implementation commit:

```text
d5e5cefaf43213f884bf88392faa5ac638267ae3
tree 853b302a84cf2045278f1a50a083563915ac97bb
```

## Lease Admission Correction

Recoverable V1 owner metadata is now validated before any process-liveness
check. Admission requires:

- the exact contested canonical session path;
- a positive integer PID no greater than `2_147_483_647`;
- nonempty token and creation timestamp;
- string, nonempty `processStartId` when present; and
- string, nonempty `activeSessionId` when present.

Malformed or mismatched metadata is classified as an unknown owner. The
contender receives the existing canonical `session_already_active` refusal,
and the lock plus owner bytes remain unaltered. A valid dead V1 daemon owner
continues to use the existing recoverable compatibility path.

The same strict reader protects best-effort recoverable release, so an owner
cannot remove a lock whose recorded session path or metadata shape no longer
matches its lease.

Owner-process evidence now has three explicit states:

```text
owner_active
owner_proven_dead
owner_unknown
```

Only `owner_proven_dead` authorizes reclamation. Explicit `ESRCH` and a verified
process-start mismatch establish that state. Matching or missing identity,
`EPERM`, invalid arguments, unsupported or unexpected probe failures, and
unexpected identity-query failures preserve the lock and refuse the contender.

## Plan Reconciliation

Historical Tasks 0-7 retain their original recorded worktree paths. Every
executable command in Tasks 8-12 now uses the active recovery worktrees:

```text
C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery
D:/prime-agent/.worktrees/task7-runtime-topology-recovery
```

The obsolete hidden-identity, fallback-surveillance, and fallback-teardown
wording was removed. No promotion step from a quarantined worktree is implied.

## Frozen Bundle Custody

The Prime package was rebuilt from the clean new commit using the same
package-local build path that avoids model-catalog generation. A new manifest
was created; prior V5 manifests remain unchanged.

```text
Prime bundle identity:
C5A4861EFFAED21EDA75C66C218F68057B6BAF116E75E620666CF1326CE69CB7

Manifest file SHA-256:
6A1B43AFFB0EC1CC27B6402E50D71C9709D400604819922238F8E596FFEA04B0

Entries: 86
Bytes: 14,010,196

Harness SHA-256:
FD2DB5B22CADBDE03BF840C66767E8CE59FA6538008B4BBC7E4DF546B2B9F188

Wrapper SHA-256:
48B5EFDA5B4A212ED4AB42A2225CF96CF1F7B6199FB4D7364C00AFF71F3C08D2

Plan SHA-256:
BE2C0D3BD1E36E8746711A4BDF0E56D372A6C0C8F9BF02053D1254B5F5A2B252
```

The wrapper now binds the exact Prime commit, bundle identity, manifest path,
and manifest-file hash above. Gate 7B lease and direct evidence roots remain
absent.

## Offline Verification

RED:

```text
Strict V1 owner regressions: 4 failed, 19 passed
Out-of-range PID acquisition/release regressions: 4 failed, 27 passed
Unexpected identity-query regression: 1 failed, 39 passed
```

The wrong-session-path, non-integral-PID, and malformed optional-identity cases
were reclaimed before the correction. The non-positive-PID case happened to
refuse through OS liveness behavior, demonstrating why validation had to move
ahead of that check. The out-of-range cases then proved that acquisition and
release both destroyed the contested lock, and the identity-query case proved
that an unexpected reader exception escaped the authority classifier.

GREEN:

```text
Prime lease and compatibility suites: 162 passed
Prime repository-wide source and test TypeScript check: passed
Prime Biome check for changed files: passed
Prime package-local AI, agent, and coding-agent build: passed
Rook runtime contract, product adapter, harness, and wrapper: 85 passed
Harness and wrapper Python compilation: passed
Prime bundle replay: 86/86 entries
Future Task 8-12 quarantine-path search: zero matches
Obsolete surveillance-wording search: zero matches
git diff/show whitespace checks: passed
```

Two incorrectly rooted verification commands across the correction history
invoked the repository workspace test script with coding-agent file filters.
The coding-agent subsets and unrelated TUI suite passed, while the agent and AI
workspaces reported that no matching test files existed. Those commands are
excluded from the gate; the exact package-scoped final 162-test command was run
independently and passed.

No Prime CLI, daemon, kernel, provider, model, Rhino, Grasshopper, MCP,
deployment, process cleanup, or Gate 7B transaction was launched by this pass.

## Disposition

The final reviewed issue was authorization at the reclamation sink. Metadata
admission is range-bound, and failure to establish liveness is no longer
converted into proof of death. Valid legacy daemon recovery remains intact only
for positively proven owner death. Gate 7B remains unauthorized pending review
of this frozen correction package.
