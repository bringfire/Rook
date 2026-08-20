# Qwen3.8 Multimodal Vessel Massing V1 Pre-Contact Report

## Status

The single-row campaign package is frozen for one authorized execution. No
Ollama model request, Qwen turn, Rook target preparation, Rhino mutation, or
Grasshopper mutation has occurred for this campaign. The intended evidence root
does not exist.

This package changes only experimental runner custody, tests, a model-free
attachment preflight, frozen protocol/adjudication artifacts, and retained image
copies. Prime, Rook product code, both Grasshopper skills, `rook_full`, and the
behavioral evaluator are unchanged.

## Frozen Inputs

- Rook repository baseline: `d654d674f5dc0f2976e0e0a4769f87fcfd1ec1d9`
- Prime runtime: `739400844f8f3f280414b0c7b9c65797208815d3`
- Optional Python skill: `2312DBF60EF17F9AA0B6503EDC281C7D367A5379F200ADEADB4747FD58A34F66`
- `rook_full`: `06F1CB4AA58FD8C4C6F61F96CE7B8A5F4FEF7B6B126D00C0550B2CB3AA0BBF74`
- Behavioral acceptance module: `8A68408AD6216A7DEF638EAC962B28CA7A32735312DCD00C57D038EAD8DEBAF5`
- Protocol: `318E6C6BD5666A99EBA71A9A5D01DE72E66DDFB18674F497253B055A546C5C4A`
- Adjudication: `AEAADD89691CCF7FD355ABD42A606B6BDD6DDD35691069DD84AE639311C9B288`
- Runner: `F46A2D71708B1114FD29F480B656874FF6C2D1757CC657C3CE33785DF07023C9`
- Attachment preflight: `C0E15D71651D2E59E2461A7D3F9A3E83AA194B0E26676AFFEDD759DFF8355DB2`

Reference images, in required attachment order:

1. `TheVessel-01.png`: `0516B550433493CCA528762659F4209219B4F9A0D07AD002AEC86CEAAD5E75AA`, 2,794,738 bytes, 1080 x 1226.
2. `TheVessel-02.png`: `8A58E062A99DA5E3F25242B7483B97C0CA459A7ABDBC089DEFCEBBDD59737BA0`, 2,930,563 bytes, 1080 x 1440.

The source files and repository copies are byte-identical.

## Configuration

- Model: `qwen3.8:27b`, low thinking, text and image input.
- Context window: 131,072.
- Compaction: enabled; 16,384 reserve tokens; 20,000 recent tokens; agent-callable.
- Goal budget: 9,500,000 provider tokens.
- Outer provider ceiling: 10,000,000 tokens.
- Gateway ceiling: 500 calls.
- Wall-clock ceiling: 10,800 seconds.
- One execution, zero retries, silent post-run evaluation.
- Evidence root: `C:/UDEV/RookEvidence/2026-08-19-qwen38-multimodal-vessel-massing-v1`.

The first model-controlled IPython action is frozen as one `attach_image` call
with both source paths in the listed order. Both resulting image blocks must be
retained before any Rook call. Post-load custody requires Ollama to report
context `131072` and `100% GPU`; otherwise the runner terminates the row.

## Model-Free Verification

The focused Python suites passed:

```text
236 passed, 11 existing warnings
```

Prime's existing active-goal compaction continuation regression passed:

```text
1 passed, 6 skipped
```

The campaign-owned model-free attachment preflight passed against both frozen
images through Prime's real IPython attachment bridge. It retained the source
hashes above and produced two ordered JPEG image blocks:

```text
Image 1: 256,652 bytes, 651142E5DDD04770A8CA4722051ABA5306BF276CDEA53706FDD8D97F0591A78C
Image 2: 256,052 bytes, D7B1829572D3CC5D92B937A79FE24A93C7BF5DB77125D21845C34F609897D663
```

A bare Prime attachment test initially refused because the sealed external
kernel does not install missing Python skills and did not contain `attach_image`.
The campaign does not modify that kernel. It exposes the exact frozen bundled
`attach-image/src` directory through the already-custodied `PYTHONPATH` and sets
`PYTHONDONTWRITEBYTECODE=1`. The dedicated preflight then passed without model or
Rook contact. Prime's known Windows immediate-temp-cleanup `EPERM` behavior is
avoided by preserving the unique preflight state directory in campaign evidence.

At this pre-contact check the machine reported 30,004 MiB free GPU memory, no
loaded Ollama model, and disabled AC standby. The live runner will recheck and
retain all three facts before target preparation.

## Execution Order

```text
repository and runtime custody
-> frozen source/frozen image equality
-> tool surface
-> goal/kernel preflight
-> GPU/Ollama/sleep/compaction/attachment preflight
-> fresh Grasshopper target preparation
-> one Qwen transaction
-> attachment and post-load custody
-> silent post-run observation and adjudication input
-> row and campaign manifests
-> report
```

The exact authorized command is:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe scripts/qwen38_self_termination_campaign_runner.py run --protocol docs/superpowers/experiments/2026-08-19-qwen38-multimodal-vessel-massing-v1.json --evidence-root C:/UDEV/RookEvidence/2026-08-19-qwen38-multimodal-vessel-massing-v1 --document-serial 268435457 --process-id 210020
```

Any failed preflight, custody check, attachment order, post-load context/GPU
check, target preparation, or runtime gate is retained as `incomplete`. There is
no retry, repair transaction, alternate model, evaluator feedback, or
configuration change.
