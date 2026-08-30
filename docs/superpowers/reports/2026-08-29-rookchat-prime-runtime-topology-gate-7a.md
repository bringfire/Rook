# RookChat Prime Runtime Topology Gate 7A

**Status:** READY FOR INDEPENDENT REVIEW; HARNESS NOT EXECUTED

**Approved continuation:** `77d6cd5bd7805f6bd3aa4cc78f001ad222fc82e6`

**Prime implementation commit:** `6f76ebd9d5c2f2a690c104313dd4cc92c58f3040`

**Prime implementation tree:** `b2428ac412401c195f89e67c7691a83497fdeb56`

## Scope

This pass executed only Task 7 Steps 0-3. It did not start Prime's CLI, a
Prime daemon, an IPython kernel, the runtime-topology harness, Rhino, a
provider, or a model. The two harness entry points are authored and unit
tested, but remain unexecuted pending Gate 7A approval.

Tasks 0-6 remain preserved. The rejected daemon-topology worktrees remain
quarantined and dirty by design: 17 Rook status entries and 8 Prime status
entries. This pass did not modify either quarantine.

## Entry custody

The implementation began from the approved continuation and preserved the
reviewed lineage:

```text
Rook HEAD:    77d6cd5bd7805f6bd3aa4cc78f001ad222fc82e6
Rook parent:  77f07f2ebbce0665130e6807bb28a7a8e96d8dc7
Rook Tasks 0-6 ancestor:
               cf760498cb51895013c7f2163e6faaa7b66255bf
Prime HEAD:   3e3c9da18911f3ecffd56fe99eb7bab552fcd81e
```

Both implementation worktrees were clean before dependency restoration and
source changes.

## Dependency custody

Dependencies were restored only into the two implementation worktrees:

```powershell
Set-Location D:/prime-agent/.worktrees/task7-runtime-topology-review
npm ci --offline --ignore-scripts --no-audit --no-fund

Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/mcp_server
uv sync --offline --frozen --extra test
```

The lockfile hashes were identical before and after restoration:

```text
package-lock.json:
C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D

uv.lock:
7BF31108A2CA69B65D9DE2936CFD7022A7E4BBE2574C3E512CBBD159B7ADE171
```

Resolution custody was checked directly:

```text
vitest:
D:/prime-agent/.worktrees/task7-runtime-topology-review/node_modules/vitest/vitest.mjs

sys.executable:
C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/mcp_server/.venv/Scripts/python.exe

rook.__file__:
C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/mcp_server/src/rook/__init__.py
```

No lifecycle scripts or network fallback were admitted.

## Prime implementation

Prime now has an explicit `--rpc-runtime daemon|in-process` selector. The
default remains daemon-backed. `--rpc-runtime in-process` is valid only in RPC
mode, conflicts with a daemon socket, and routes through Prime's existing
in-process RPC runtime.

The direct branch activates Prime's existing saved-session lease internally
with a fresh process-owned identity. Rook does not supply Prime's internal lease
environment fields.

Windows lease identity probing is hidden, noninteractive, bounded to two
seconds, and non-retried. The exact upstream Windows kernel-bootstrap correction
from `142045138b8679ec077f8f032d2befe66ca5606b` is reconciled without advancing
other upstream behavior.

## Rook implementation

Rook now defines a closed Prime artifact manifest over every regular file in
exact `dist/bundle` and `dist/skills`, with no exclusions and a required
`bundle/cli.js`. Verification recomputes all bytes before admitting the bundle.

The Rook-owned fallback cleanup path requires the retained direct-child PID,
parent PID, process-start ticks, and launch generation. It performs at most one
hidden bounded `taskkill /PID <pid> /T /F`. A zero taskkill exit is not accepted
as success until the exact direct child handle also reports exit. Timeout,
identity drift, or an unsettled child is terminal uncertainty; no retry or
wider cleanup follows.

The authored harness has only these entry points:

```text
lease-sequence
direct-vertical
```

It uses a closed credential-free child environment, exact argument arrays,
`--offline`, unique run roots, one canonical resumed session file, explicit
reviewer-frozen bundle and skill manifest hashes, a preflighted `uv.exe`, and
hidden exact-generation teardown. It sends no prompt. Its runtime process
monitor uses Windows APIs in-process and launches no identity probe.

## Frozen identities

The committed Prime build produced this external closed manifest:

```text
Manifest path:
docs/superpowers/experiments/inputs/2026-08-29-rookchat-prime-runtime-topology-gate-7a/prime-bundle-manifest.json

Bundle manifest identity:
8CB71BB3EC174ABF0F4CDBC45DAB0C0058375F635712FC52E41B2FBC9E4A5029

External manifest file SHA-256:
72002BAEE857DE9BE7E959A1EB3B6997F27EB98F7FDF2282B76BBFEA8813B12E

Entries: 86
Total bytes: 14,004,768
```

The source package manifests proposed for Gate 7B are:

```text
Prime goal skill:
D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7

Rook product skill:
29CF64B14640C3D566B4E2A0D5E766359E696C6E53E47EDAAC11E6E5121011AF
```

The preflighted executable identities are:

```text
Node:
C:/Program Files/nodejs/node.exe
F13AC3CA23248DC389507E8FE38C34489AB7EDB3E6D6700EB6DA6A0B7E128EAF

uv:
C:/Users/bring/AppData/Local/hermes/bin/uv.exe
68A22CBAB1674647BCDA32120B214E6480F875414E3333F49F87AE99B4B0E0FA
```

## Offline verification

Prime:

```text
Parser, routing, and Windows-bootstrap tests: 164 passed
Injected Windows identity and in-process lease tests: 3 passed, 6 skipped
Package TypeScript build and bundle: passed
git diff --check: passed
```

Rook:

```text
Focused manifest, cleanup, harness-contract, and argv tests: 25 passed
Final focused manifest, cleanup, and harness-contract tests: 24 passed,
27 deselected
Python compilation for every changed/new Python file: passed
git diff --check: passed, with existing line-ending conversion warnings only
```

An additional broader runtime-contract test command produced 44 passes and one
failure in the pre-existing checked-in `rook-full/package-manifest.json` parity
test. The checked-in manifest does not reproduce this clean worktree's package
bytes: Windows checkout line-ending conversion changes the four admitted text
files, and the recorded `pyproject.toml` entry also differs from the Git blob.
This pass did not modify the product skill or retroactively change Tasks 0-6.
The Gate 7A harness instead requires explicit expected source-manifest hashes
and rechecks them before creating its run root. The existing checked-in product
manifest discrepancy remains a separately visible prerequisite before later
product deployment; it is not hidden as a passing result here.

The complete `session-lease.test.ts` file was not used as the final gate. An
earlier exploratory run reproduced four existing Windows `EPERM` failures in
the unchanged directory-lease rename harness while the new injected tests
passed. No retry, timeout change, or unrelated repair was made.

## Unexecuted Gate 7B commands

The proposed evidence roots do not exist. After independent approval, the
lease sequence is run first. The direct vertical is admitted only if the lease
sequence passes. The exact proposed commands are:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/mcp_server
$python = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/mcp_server/.venv/Scripts/python.exe'
$script = 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/scripts/rookchat_prime_runtime_topology_harness.py'
$common = @(
    '--node-path', 'C:/Program Files/nodejs/node.exe',
    '--node-sha256', 'F13AC3CA23248DC389507E8FE38C34489AB7EDB3E6D6700EB6DA6A0B7E128EAF',
    '--prime-dist-root', 'D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/dist',
    '--prime-bundle-manifest', 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/docs/superpowers/experiments/inputs/2026-08-29-rookchat-prime-runtime-topology-gate-7a/prime-bundle-manifest.json',
    '--prime-bundle-sha256', '8CB71BB3EC174ABF0F4CDBC45DAB0C0058375F635712FC52E41B2FBC9E4A5029',
    '--uv-path', 'C:/Users/bring/AppData/Local/hermes/bin/uv.exe',
    '--uv-sha256', '68A22CBAB1674647BCDA32120B214E6480F875414E3333F49F87AE99B4B0E0FA',
    '--model', 'openai-codex/gpt-5.6-sol',
    '--goal-skill', 'D:/prime-agent/.worktrees/task7-runtime-topology-review/packages/coding-agent/skills/goal/SKILL.md',
    '--goal-skill-manifest-sha256', 'D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7',
    '--rook-skill', 'C:/UDEV/Rook/.worktrees/task7-runtime-topology-review/integrations/prime/skills/rook-full/SKILL.md',
    '--rook-skill-manifest-sha256', '29CF64B14640C3D566B4E2A0D5E766359E696C6E53E47EDAAC11E6E5121011AF'
)

& $python $script lease-sequence `
    --run-root 'C:/RookEvidence/2026-08-29-rookchat-prime-runtime-topology-gate-7b-lease' `
    @common

# Run only after the lease-sequence result is independently admitted.
& $python $script direct-vertical `
    --run-root 'C:/RookEvidence/2026-08-29-rookchat-prime-runtime-topology-gate-7b-direct' `
    @common
```

No command in this section was executed. No Gate 7B evidence root was created.

## Disposition

Gate 7A stops here for independent review. No process-boundary, lease-sequence,
direct-runtime, kernel, provider, model, Rhino, or live product execution is
authorized by this report.
