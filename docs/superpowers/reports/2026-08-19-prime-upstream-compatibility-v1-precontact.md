# Prime Upstream Compatibility V1 Pre-Contact Gate

**Date:** 2026-08-19
**Status:** Ready for independent pre-contact review
**Live/model contact:** None in the admitted V2 lane
**Smoke execution:** Not started or authorized

## Question

Can current Prime upstream become the next Rook evaluation baseline while
preserving the structured MCP-error behavior required by `rook_full` and the
goal, skill, compaction, and IPython-state behavior already used by the Qwen3.8
campaigns?

This is an offline compatibility gate. It makes no claim about Qwen behavior,
Grasshopper authoring, runtime efficiency, or deployment readiness.

## Exact Source Custody

The admitted worktree is:

```text
D:/prime-agent/.worktrees/rook-upstream-evaluation
```

It was created from the exact upstream commit, not from a moving branch:

| Item | Identity |
|---|---|
| Upstream commit | `f8f0036cc2da1a640aad990ae8dcb7c4820ce32e` |
| Upstream tree | `3ff69db27820afc0f3addc2089f6c04f10808d21` |
| Source patch commit | `30a6621bca698ef14f64e5e45c5b1b6364148789` |
| Source patch tree | `05021548c143700b1b24045d29e712f784797798` |
| Result commit | `739400844f8f3f280414b0c7b9c65797208815d3` |
| Result tree | `4d782187c6898aa8352045dd597bab6a3819029c` |
| `package-lock.json` | `C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D` |

The applied result differs from upstream in exactly two files:

```text
prime-agent-runtime/src/rlm/mcp_base.py
prime-agent-runtime/test/test_mcp_base.py
```

The Prime worktree is clean. The primary Prime checkout remains at
`c98941a2a5cf40faecf9b4648ac3c304abf48fd3`; the historical qualified runtime
remains detached at `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`.

## Isolation Proof

The offline gate used only the admitted worktree for Prime Node and Python
code:

- `tsx` and `vitest` resolved under the admitted worktree's `node_modules`.
- The imported IPython provisioner resolved from the admitted worktree.
- `goal.__file__` resolved from the admitted worktree.
- `rlm.mcp_base.__file__` resolved from the admitted worktree.
- The sealed interpreter was
  `C:/Users/bring/.prime/agent/kernel-venv/Scripts/python.exe`.
- The Rook adapter resolved from this Rook worktree, as intended.
- A scan of the final textual evidence found no reference to either historical
  Prime worktree or the discarded evaluation sibling.

The sealed interpreter receives Prime Python source through an explicit
`PYTHONPATH`; it does not import an installed Prime package.

## Offline Results

### Dependencies and builds

Dependencies were reconstructed with:

```text
npm ci --ignore-scripts --offline --no-audit --no-fund
```

This installed 352 packages from the frozen lock without lifecycle scripts.
The branch-local `tsgo` compiler then passed for:

```text
packages/tui/tsconfig.build.json
packages/ai/tsconfig.build.json
packages/agent/tsconfig.build.json
packages/coding-agent/tsconfig.build.json
```

The root build script was deliberately not used in the admitted lane because
it generates model catalogs through network services.

### Structured MCP failures

The exact patched Python suite passed:

```text
22 passed in 0.45s
```

This includes preservation of the exact `structuredContent` object while the
same `McpToolError` control flow remains raised.

### Skills, goals, compaction, and state contracts

Eight branch-local Node suites passed:

```text
8 files passed
289 tests passed
```

The retained suite covers:

- parsing explicit `--skill` paths;
- loading explicit skill paths;
- expanding `/skill:test` before the provider prompt;
- staged host-request contracts;
- goal lifecycle and budget behavior;
- active-goal continuation after successful threshold compaction;
- interrupted-loop continuation after compaction; and
- IPython snapshot/restore code and metadata handling.

### Managed-kernel preflight

The versioned model-free preflight uses Prime's real
`IpythonKernelProvisioner` with the sealed Windows kernel. It proved:

```text
goal.get()                 active, token budget 1,900,000
goal.complete()            complete
oversized variable         detected and pruned
small sentinel             retained after pruning
kernel restart             sentinel restored
pruned variable restart    remained absent
goal after restart         complete
first and second kernels   closed
```

The preflight created a 17 MiB variable, which exceeded Prime's 16 MiB
per-variable snapshot limit. Prime excluded and pruned that variable while
retaining a small sentinel. A fresh kernel restored the sentinel and the
completed goal state. The preflight result records both Node and Python source
paths and refuses if either Prime import is outside the admitted worktree.

The preflight source SHA-256 is:

```text
651AF08A80E1DB5CAFB58D3E5B07BF52512BB35DDD620F319ED37F3B1AA50EC7
```

### Upstream Windows test-harness limitation

The upstream `kernel-goal-skill` and `kernel-state-roundtrip` suites do not
produce a clean test exit on this Windows host:

```text
2 files failed
10 failed, 1 passed
```

All ten reported failures occur after their functional bodies, when the test
immediately calls recursive `rmSync` and Windows returns `EPERM` for a kernel
temporary directory whose handles are still releasing. The full nonzero log is
retained. This report does not relabel those tests as passing.

The durable preflight avoids that cleanup assertion, retains its state files as
evidence, closes both kernels, and independently proves the specific goal and
large-state behaviors required by this gate. No qualification-owned process
remained afterward.

## Discarded First Attempt

The first evaluation sibling invoked Prime's root build. That build contacted
model-catalog metadata services before the behavior was noticed. No model
inference, Rook MCP, Rhino, or Grasshopper contact occurred, but the lane was
not offline and was rejected.

It remains preserved at:

```text
D:/prime-agent/.worktrees/rook-upstream-evaluation-contaminated-v1
```

The admitted V2 worktree was then recreated from the exact upstream commit and
used only offline dependency installation, direct compilation, tests, and the
model-free kernel preflight. This report therefore makes no false zero-network
claim about the overall work session; it claims no network contact in the
admitted V2 lane.

## Evidence

Durable evidence root:

```text
C:/UDEV/RookEvidence/2026-08-19-prime-upstream-compatibility-v1
```

The final manifest covers 12 selected files and independently verifies with
zero mismatches:

```text
CC873C6FEC5BD8BE22E9C9E5D9E7F2132F70F3B1815E24CE99F31F4B8961D953
```

Preliminary preflight V1/V2 files remain outside the admitted manifest. The
manifest admits only the final post-install V3 preflight, custody and isolation
records, build/test logs, and final process ledger.

## Disposition

The exact upstream-plus-patch candidate is ready for independent pre-contact
review. The offline evidence supports compatibility at the required boundary:

- exact source and dependency custody;
- branch-local Node and Python imports;
- preserved structured MCP failures;
- explicit skill loading;
- public goal operations;
- goal continuation through compaction; and
- bounded large-IPython-state pruning without loss of retained state.

The upstream Windows cleanup race remains a real test-harness defect and is not
a Rook product qualification. It does not justify changing Prime or bypassing
the retained functional preflight in this slice.

No smoke task should run before independent approval. After approval, the next
bounded action is one `T3` point-row repair smoke derived from the previously
qualified V3 row, with its model, thinking level, task, skill, adapter, target
fixture, budgets, runner behavior, and evaluator frozen. The only intended
runtime change is the admitted Prime source/result above. Python-skill packaging
remains paused.
