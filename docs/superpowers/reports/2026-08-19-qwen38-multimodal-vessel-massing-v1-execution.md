# Qwen3.8 Multimodal Vessel Massing V1 Execution

**Date:** 2026-08-19
**Disposition:** `incomplete - pre-target Python environment custody drift`
**Actor/model contact:** None
**Grasshopper target preparation:** None
**MV1 row executions:** Zero

## Authorized Transaction

The exact frozen single-run command was invoked once from clean preparation
commit `da9e15b11366462769ed4d802e6f7882e7742e44`:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  scripts/qwen38_self_termination_campaign_runner.py run `
  --protocol docs/superpowers/experiments/2026-08-19-qwen38-multimodal-vessel-massing-v1.json `
  --evidence-root C:/UDEV/RookEvidence/2026-08-19-qwen38-multimodal-vessel-massing-v1 `
  --document-serial 268435457 `
  --process-id 210020
```

The runner stopped during pre-target Python environment admission with:

```text
RuntimeError: python_environment_drift:kernelSitePackages
```

It did not prepare the Grasshopper target, launch the Qwen Actor, load an
Ollama model, mutate the canvas, run the silent evaluator, or retry.

## Completed Preflight Work

Before refusing the transaction, the runner retained and passed:

- 236 pre-contact tests with 11 existing dependency warnings;
- exact Prime, Rook, runner, skill, adapter, model, and image custody;
- Prime's disposable `goal.get()` and `goal.complete()` bridge preflight;
- the upstream compaction-continuation test;
- both source-image hashes and ordered attachment conversion;
- no model or Rook contact during attachment preflight;
- 29,974 MiB free GPU memory against the 27,000 MiB minimum;
- no loaded Ollama model; and
- zero AC standby timeout.

The attachment preflight converted the two frozen source images in the
required order:

```text
Image 1 source SHA-256
0516B550433493CCA528762659F4209219B4F9A0D07AD002AEC86CEAAD5E75AA

Image 1 attached JPEG SHA-256
651142E5DDD04770A8CA4722051ABA5306BF276CDEA53706FDD8D97F0591A78C

Image 2 source SHA-256
8A58E062A99DA5E3F25242B7483B97C0CA459A7ABDBC089DEFCEBBDD59737BA0

Image 2 attached JPEG SHA-256
D7B1829572D3CC5D92B937A79FE24A93C7BF5DB77125D21845C34F609897D663
```

## Exact Custody Failure

The frozen protocol admitted this sealed-kernel site-packages inventory:

```text
entry count
14,915

total bytes
302,687,750

manifest SHA-256
019A431AA3EC558A0068215D513E59AB732FDDCCFD20DDCADD7B58E56A0153ED
```

The authorized run observed:

```text
entry count
14,916

total bytes
302,698,244

manifest SHA-256
7ED807593216A4ECA17A142CDB80BBF633B993C5CEFCBAC26FE2B1F75ADF0E89
```

The exact additional file was:

```text
C:/Users/bring/.prime/agent/kernel-venv/Lib/site-packages/
  zmq/utils/__pycache__/garbage.cpython-311.pyc

bytes
10,494

SHA-256
117D3D336DDE34C07DAD67F6426110908A4F5B6B68640787757B489279CE250D

creation and last-write time (UTC)
2026-08-20 03:06:51
```

That timestamp predates the authorized campaign, whose retained protocol was
created at 2026-08-20 03:17:11 UTC. The bytecode was produced by the earlier
model-free attachment-development probe before that probe was changed to use
`PYTHONDONTWRITEBYTECODE=1`. The authorized preflight did not create it.

The runner therefore detected pre-existing contamination caused by campaign
development and refused exactly as designed. The file was not deleted and the
transaction was not retried.

## Evidence

Durable evidence root:

```text
C:/UDEV/RookEvidence/2026-08-19-qwen38-multimodal-vessel-massing-v1
```

The runner sealed and verified every retained entry:

```text
manifest SHA-256
259A5C46DB0E643EE8487AE9AB0969EC22EDFF2857E1304383BAE4807CA703CD

entry count
26/26

mismatches
0
```

Post-run inspection found no loaded Ollama model and no campaign-owned process.
Both the Rook campaign worktree and Prime evaluation worktree remained clean.

## Disposition

This transaction supports no claim about Qwen3.8 multimodal reasoning,
Grasshopper authoring, massing semantics, receipt discipline, or completion.
The Actor never ran.

The result is an authentic `incomplete`, not a model failure. The frozen V1
protocol permits one execution and no retry, so its evidence and classification
remain unchanged. Any future attempt requires a separately frozen evidence root
and reviewed custody baseline; this execution authorizes neither cleanup nor a
V1 rerun.
