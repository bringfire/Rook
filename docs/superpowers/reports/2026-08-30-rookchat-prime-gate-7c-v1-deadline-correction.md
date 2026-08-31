# RookChat Prime Gate 7C V1 Deadline-Inversion Correction

**Status:** OFFLINE CORRECTION COMPLETE; GATE 7C V2 NOT FROZEN OR EXECUTED

## Scope

Gate 7C V1 remains permanently preserved as failed evidence. This correction
changes only Rook's deadline selection for Prime runtime preparation and the
causal model-free tests around that boundary. It does not change Prime, the RPC
topology, runtime-contract custody, ordinary control deadlines, cleanup,
retries, or process ownership.

## Retained V1 Evidence

- Approved Rook execution commit:
  `fa9ec0dfb88f2389b754884eb9095163dfcf751b`
- Prime commit:
  `46dbf2749d64446820fbf31e52d8766e5ee87be9`
- Evidence root:
  `C:/RookEvidence/2026-08-30-rookchat-prime-gate-7c-broker-v1`
- `admission.json` SHA-256:
  `0D7BCAE87242A366C6EBE07FD5A91B8696A52ABD1F6A0838FAAD2E99FAAAB43A`
- `result.json` SHA-256:
  `D891E82E19B86F8C3709ADF57860F72848BB260D9A5A32AD351B6F810AA44E09`
- V1 result: `failed`
- V1 failure:
  `Prime control command timed out: prepare_ipython_runtime`
- V1 prepared record: absent

No V1 evidence file was rewritten and no V1 command was rerun.

## Root Cause

`PrimeRpcProcess.command()` correctly keeps ordinary control commands bounded
by a 10-second default. `PrimeChatBackend._prepare_runtime()` previously called
`prepare_ipython_runtime` without an explicit timeout, so that semantically
long operation inherited the generic 10-second deadline.

Prime's unchanged `prepareIpythonRuntime()` owns a 120-second internal deadline.
The V1 contract environment and package installation completed at approximately
the same time Rook abandoned the response. Rook then retired the exact owned
child while Prime was still settling the command. This is deadline inversion,
not evidence of daemon participation, target drift, or runtime-contract failure.

## Correction

Rook now defines one named preparation deadline:

```python
RUNTIME_PREPARATION_TIMEOUT_SECONDS = 150.0
```

Only the `prepare_ipython_runtime` broker call receives that explicit value.
The 30-second response grace sits outside Prime's 120-second internal bound.
Every ordinary control command retains the existing 10-second default.

No cleanup deadline was changed. A preparation timeout still removes the
pending response waiter, ignores any late correlated response, leaves the
registry preparation state pending, retires the exact resident, and admits no
automatic replay.

## Causal Coverage

The tests establish:

- an absent kernel root before first-use preparation;
- preparation may outlive the configured generic control deadline and settle;
- ordinary controls still use the generic bounded deadline;
- the broker passes exactly 150 seconds only to runtime preparation;
- preparation timeout leaves the durable prepared record unset;
- a late preparation response is ignored after timeout; and
- successful preparation followed by retirement exits gracefully.

## Offline Results

- Process and broker causal tests: **35 passed**.
- Complete focused Gate 7C suite: **59 passed**.
- Python compilation: passed.
- Prime worktree: unchanged.
- No Prime runtime, kernel, provider, Rhino, Grasshopper, or Gate 7C command was
  launched during this correction.

Frozen changed-file SHA-256 values before commit:

- `prime_backend.py`:
  `4FD7A8A11FE50F9A63902E0499239CBEBCC07F66278D68B099694879E49EA9A6`
- `prime_rpc_fake_child.py`:
  `26D7C3A4F11243506C1F5DE67C08EFA8999EBA00514EFCC355B9472C56E71236`
- `test_prime_process.py`:
  `6E7D779F0DC0F6D6D920217D71BCEB1E2A4F7BB6CFBF7050CB667187603935C3`
- `test_prime_runtime_broker.py`:
  `2280AEDAC8A7CF8754AE09CFD22DEB3A80DD5BC0A538566E6C38EE6551A00634`

## Review Gate

Gate 7C V2 remains unauthorized. After independent review, V2 must receive a
new versioned configuration, evidence root, kernel root, wrapper custody, and
one-execution authorization. V1 must remain untouched. No retry, timeout tuning,
or warm-environment reuse is admitted.
