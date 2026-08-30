# RookChat Prime Runtime Topology Gate 7B V5 Execution

Status: PASSED; EVIDENCE SEALED; GATE 7C NOT AUTHORIZED

Date: 2026-08-30

## Scope

This report records the one authorized model-free Gate 7B V5 transaction. It
qualifies the reviewed direct in-process Prime topology through the lease
sequence and the direct runtime-preparation vertical. It does not qualify the
RookChat broker integration, authorize Gate 7C, or make a product cutover
decision.

No retry, prompt repair, timeout adjustment, daemon redesign, process
surveillance, or manual runtime repair occurred.

## Frozen Admission

The externally authenticated wrapper was:

```text
C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery/scripts/
run_rookchat_prime_runtime_topology_gate_7b.py

SHA-256:
48B5EFDA5B4A212ED4AB42A2225CF96CF1F7B6199FB4D7364C00AFF71F3C08D2
```

The wrapper admitted these reviewed owners:

```text
Prime commit:
46dbf2749d64446820fbf31e52d8766e5ee87be9

Rook commit:
d968d680852fcfa14e001756d988539429fac3d8

Harness SHA-256:
FD2DB5B22CADBDE03BF840C66767E8CE59FA6538008B4BBC7E4DF546B2B9F188

Prime bundle identity:
C5A4861EFFAED21EDA75C66C218F68057B6BAF116E75E620666CF1326CE69CB7

Goal package manifest:
D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7

rook-full package manifest:
2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678
```

The wrapper SHA-256 was checked outside the wrapper before Python execution.
The transaction exited `0` after 22.5 seconds. It was invoked exactly once.

## Lease Sequence

The lease row passed with transaction ID:

```text
837e86e1a5ad4bc28f5b788e8e65b5e2
```

The first owner created and persisted this exact session:

```text
Session ID:
01a054cd-ec05-75ca-9538-2a81b947937e

Session file:
C:/RookEvidence/2026-08-30-rookchat-prime-runtime-topology-gate-7b-v5-lease/
sessions/01a054cd-ec05-75ca-9538-2a81b947937e.jsonl
```

Its model-free `set_rlm_max_depth` call returned exactly:

```json
{"maxDepth":0,"source":"chat"}
```

While that owner remained live, a second process used `--resume` with the same
canonical session file. Prime refused it with the exact structured startup
outcome:

```json
{
  "type": "rpc_startup_error",
  "code": "session_already_active",
  "sessionPath": "<the exact canonical session file above>"
}
```

After the first owner closed gracefully with exit code `0`, the third process
resumed that exact file. Its `get_state` response retained both the original
session ID and the original session file. It then closed gracefully with exit
code `0`.

The refusal process exited `1` as required by the refused startup. Its closure
was recorded as graceful; it was not accepted as a normal owner settlement.

## Direct Runtime Vertical

The direct row passed with transaction ID:

```text
820551fb19994f8d9a4d616781ec86bd
```

The exact Prime launch selected:

```text
--mode rpc
--rpc-runtime in-process
--offline
--tools ipython
--no-extensions
--no-skills
--no-context-files
--no-prompt-templates
```

Only the frozen goal and `rook-full` skill paths were supplied. The direct
owner completed these model-free commands successfully:

```text
get_state
set_rlm_max_depth
get_rlm_max_depth_status
prepare_ipython_runtime
```

Both recursion responses reported `{maxDepth: 0, source: "chat"}`. Runtime
preparation selected the evidence-root contract environment and proved:

```text
goal import:      inside the staged frozen goal package
rook_full import: inside the staged frozen rook-full package
rook_full.call:   available
rook_full.read:   available
rook_full.search: available
```

The direct owner closed gracefully with exit code `0`. The four retained owner
PIDs from the lease and direct rows were absent after settlement.

## Evidence Custody

The two evidence roots were sealed after execution with the repository's
existing non-self-referential `rook.evidence_manifest:v1` algorithm. The
manifest and its verification record are the only excluded files.

```text
Lease evidence root:
C:/RookEvidence/2026-08-30-rookchat-prime-runtime-topology-gate-7b-v5-lease

Entries: 150
Manifest SHA-256:
628E041AF8C8B9776630F811D382FD9909A5BB7E635F494A0B77B01F05281605
Mismatches: 0

Direct evidence root:
C:/RookEvidence/2026-08-30-rookchat-prime-runtime-topology-gate-7b-v5-direct

Entries: 15,829
Manifest SHA-256:
B4C7854CC2DA2EE2ADFFA860A7E79102B3D1EC1EDB3D76EB207DB2BE4625301F
Mismatches: 0
```

The larger direct manifest includes the generated contract environment rather
than recording only selected result files.

## Boundaries

This was an offline, model-free runtime-topology qualification. It did not
send a prompt, contact a provider or model, start Rhino or Grasshopper, call
Rook, mutate a document, deploy product artifacts, or exercise the RookChat
broker.

The pass establishes the reviewed Gate 7B sequence:

```text
one direct in-process owner
-> exact Prime-owned live-session refusal
-> graceful owner close
-> same-session reopen
-> contract-keyed IPython runtime preparation and import custody
-> graceful direct settlement
```

It does not establish Gate 7C behavior, live panel behavior, or the later
Slice 3 and Slice 4 product qualification gates.

## Disposition

Gate 7B V5 is classified `passed`. Both evidence roots are sealed and retained.
Execution stops here for independent review. Gate 7C and broker integration
remain unauthorized.
