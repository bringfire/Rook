# Local LLM Inference Fidelity: Source Review and Rook Implications

**Date:** 2026-08-23  
**Status:** Research note; no runtime change or qualification claim  
**Primary source:** [Why your local LLM feels dumber than it is](https://forum.level1techs.com/t/why-your-local-llm-feels-dumber-than-it-is/253917), `thr3e`, Level1Techs Forums, begun 2026-08-16 and reviewed through the 2026-08-23 update  
**Contact:** Read-only web and local-artifact inspection; no Prime, Ollama, Qwen, Rhino, Grasshopper, or Rook runtime contact

## Purpose and Source Custody

This note preserves the source, evaluates the strength and limits of its
evidence, and relates it to the retained Prime/Qwen/Rook campaigns. It does not
copy the evolving forum series into the repository. The source remains
attributed to its author at the URL above; this document is an independent
summary and analysis.

The forum series is a technically serious, hypothesis-generating empirical
report. It is not a peer-reviewed paper, a released reproducibility package, or
a universal benchmark. Its strongest contribution is not the headline that a
local model becomes "dumber." It is the narrower proposition that model
capability belongs to the complete inference implementation, and that
long-context tool use can expose consequential differences hidden by short
benchmarks.

That proposition is consistent with Rook's existing empirical-model-
intelligence principle. It also exposes one concrete omission in the retained
Qwen campaign custody: model bytes and nominal context were pinned, but the
effective KV-cache dtype and attention backend were not.

Related retained Rook evidence:

- [Empirical Model Intelligence](../2026-08-14-empirical-model-intelligence-principle.md)
- [Varied Product Cohort V1 Efficiency Attribution](2026-08-18-qwen38-varied-product-cohort-v1-efficiency-attribution.md)
- [Qwen3.8 Multimodal Vessel Massing V5](2026-08-20-qwen38-multimodal-vessel-massing-v5-execution.md)
- [Prime Compaction Trace Reconciliation](2026-08-20-prime-compaction-trace-reconciliation-v1.md)

## What the Forum Experiments Report

### Attention implementation

The author replayed a roughly 100,000-token network-automation workstream with
the official Qwen3.6-27B BF16 checkpoint and BF16 KV cache. Hardware, weights,
prompt history, and most runtime settings were held fixed while the full-
attention backend changed among FlashAttention 2, FlashInfer, and Triton.
Full-vocabulary logits were sampled every 32 prompt tokens under a forced common
history.

In that setup, repeated runs through the same backend were reported as
bit-identical, while different backends developed clustered, prompt-dependent
top-1 disagreements later in the prompt. Selected disagreement roots were then
allowed to branch. Some branches produced wrong interface names, commands, or
tool calls.

The numerical premise is ordinary rather than exotic: floating-point addition
and multiplication are not associative, so different parallel evaluation
orders can accumulate different rounding results. NVIDIA documents this
directly in its [CUDA C++ Best Practices Guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html),
and current vLLM documentation confirms that several attention backends exist,
can be selected explicitly, and otherwise are chosen according to hardware and
configuration in [Attention Backend Feature Support](https://docs.vllm.ai/en/latest/design/attention_backends/).
Those primary sources support the plausibility of backend-dependent numerical
differences. They do not independently validate the forum's measured rates or
its particular failure examples.

### KV-cache precision

Keeping BF16 weights and a fixed Triton path, the author compared BF16, int8,
and int4 KV caches. The lower-precision caches diverged from the BF16 numerical
reference; one selected tool-call branch reportedly recovered under int8 and
did not under int4.

This is evidence that KV-cache precision can be behaviorally material in the
tested workload. It does **not** establish a universal 40,000-token collapse
threshold. The author later emphasizes that divergence was clustered,
prompt-dependent, and only sparsely sampled in the first charts.

Ollama exposes this exact runtime choice. Its [FAQ](https://docs.ollama.com/faq)
documents `OLLAMA_KV_CACHE_TYPE`, describes `f16` as the default, and makes
quantized KV cache conditional on Flash Attention. This makes KV precision a
configuration fact that can and should be captured in an Ollama qualification.

### Weight and kernel precision

With BF16 KV cache forced, the author compared BF16 weights with several FP8,
INT8, NVFP4/mixed, and AWQ W4A16 checkpoints. In the reported workload, the
W8A16 INT8 path stayed closest to the BF16 numerical reference, while some
four-bit paths produced substantially more top-1 disagreement and malformed or
wrong operational calls.

The result is specific to the complete checkpoints, kernels, exclusions,
calibration choices, hardware, and prompt. It does not support a simple rule
that every eight-bit model is good or every four-bit model is bad. It does
support treating a quantization label as insufficient custody.

### Modified Qwen3.8 derivatives

The later forum installment compares stock Qwen3.8-27B BF16 with four BF16
"abliterated" or "uncensored" derivatives. The author reports relatively small
changes for two derivatives and materially larger structured-output damage for
two others. One derivative combined several modifications, so its observed
damage cannot be attributed to abliteration alone. The author also states that
"invalid branch futures" are invalid outputs among selected divergence roots,
not a global failure rate.

This section reinforces a useful custody rule: a derivative's base-model name
does not characterize its operational capability. The complete weight recipe
and runtime must be qualified.

## Methodological Strengths

- The workload is long-context, tool-bearing, and drawn from real work rather
  than a few isolated prompts.
- The main comparisons attempt to vary one runtime dimension while retaining a
  common history.
- Same-backend repeatability controls were included for the reported setup.
- The author distinguishes numerical fidelity from correctness: BF16 is a
  reference, not an oracle.
- The work distinguishes distribution movement, top-1 disagreement, and actual
  branched continuations.
- Later posts explicitly narrow early claims and acknowledge sparse sampling,
  prompt dependence, and storage-driven methodology changes.

## Limits and Overclaims to Avoid

1. **No universal degradation curve is established.** Early plots sample about
   three percent of positions in one principal workstream. Later selected
   ranges are denser but still selected.
2. **Top-1 disagreement is not task failure.** It is a counterfactual branch
   root under a forced history. A continuation can recover, remain equivalent,
   improve, or fail.
3. **KL divergence is not intelligence or correctness.** It measures movement
   from a chosen distribution and depends on direction and aggregation.
4. **BF16 is not semantic ground truth.** It is the higher-fidelity numerical
   reference used by the experiment.
5. **The 40K headline is not a qualified threshold.** The author's own later
   explanation says disagreement is highly prompt-dependent.
6. **The tensor-parallelism observation is suggestive, not a general NCCL
   diagnosis.** TP1, TP2, and TP4 behavior in one branch does not establish a
   universal topology rule.
7. **The sampler aside is plausible but not established by these experiments.**
   Qwen's official [Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B)
   recommends thinking-mode sampling at temperature 1.0, top-p 0.95, and top-k
   20. That supports using the published configuration; it does not prove that
   low temperature caused any particular loop.
8. **The full harness and corpus are not yet available for independent
   reproduction.** The measurements should therefore be treated as credible
   external evidence and a source of testable hypotheses, not adopted as local
   fact.

## What Our Retained Qwen Configuration Actually Establishes

The retained Qwen campaign protocols and local content-addressed model artifact
establish the following:

| Dimension | Retained fact |
|---|---|
| Model selector | `ollama_chat/qwen3.8:27b` |
| Ollama runtime | `0.32.14`, executable SHA-256 `11D7729C...A9B54` |
| Model manifest | SHA-256 `22130167...79643` |
| Weight artifact | `Q4_K_M`, 16,810,714,464-byte model layer |
| Sampler blob | temperature `1`, top-p `0.95`, top-k `20`, min-p `0`, presence penalty `0`, repeat penalty `1` |
| Vessel V5 loaded state | 100% GPU and 131,072-token context reported by `ollama ps` |
| Prime configuration | low thinking; threshold compaction enabled for Vessel V5 |

The sampler blob matches Qwen's published thinking-mode defaults. The campaigns
therefore do not support a retrospective claim that an incorrect nominal
temperature caused the observed Qwen behavior.

The Qwen weight artifact was not stock BF16. It was a roughly 17 GB `Q4_K_M`
GGUF path. The campaigns qualify successes and failures of that artifact in the
frozen Prime/Rook context; they do not establish the capability ceiling of the
stock Qwen3.8-27B checkpoint.

Two inference dimensions were not admitted by the campaign custody:

- the effective `OLLAMA_KV_CACHE_TYPE`; and
- the effective Flash Attention or other attention/backend path.

The protocols pinned the Ollama executable, model manifest and layers, Prime
runtime, request-facing context window, and post-load context/GPU state. They
did not record the Ollama server's launch environment or an engine-reported
attention backend. The current machine environment on 2026-08-23 is not valid
evidence of the environment used on 2026-08-18 or 2026-08-20, so those
historical values remain unknown.

## Relationship to Our Existing Findings

### What remains true

- The successful Grasshopper definitions and receipt-fenced observations are
  authentic. Runtime-fidelity uncertainty does not erase successful geometry.
- Rook truthfulness defects such as missing parameter connection projections
  were real host defects and were correctly repaired.
- The measured provider-token cost from repeatedly processing a growing Prime
  transcript remains real. Cumulative token totals are not the same as one
  active context, and the efficiency attribution already distinguishes them.
- Prime's 3.54 GB JSON stream problem was cumulative event serialization, not a
  3.54 GB model context or KV cache. It is a separate storage issue.
- Skill, adapter, discovery, and evidence-projection changes demonstrably
  changed behavior. Numerical fidelity is an additional variable, not a
  replacement explanation.

### What should be narrowed

We should describe the retained campaigns as evidence about **Qwen3.8-27B
`Q4_K_M` through Ollama 0.32.14 in the frozen Prime/Rook operational context**,
not unqualified evidence about raw Qwen3.8-27B capability.

Late-run tool mistakes, exact-literal errors, repetition, and strategy churn
remain multiply explainable. They may arise from model judgment, long and noisy
context, prompt projection, model quantization, KV precision, backend math, or
their interaction. The forum report upgrades inference fidelity from a vague
possibility to a concrete confounder worth freezing and testing. It does not
retrospectively attribute any Rook run to that confounder.

Prime compaction may help twice: it reduces repeated information flow and keeps
the active context shorter. But it also rewrites context through a summary. It
must therefore be qualified for evidence retention; it is not a free numerical
fidelity repair.

## Smallest Useful Follow-Up

Do not build a full-logit laboratory, alter Rook semantics, or rerun the broad
campaign yet.

First perform one model-free runtime-custody audit and close the measurement
gap for future runs. Record, without secrets:

- exact model and projector blob hashes and quantization metadata;
- Ollama executable/version and server process start identity;
- GPU model, driver, loaded processor split, and actual loaded context;
- server launch values for `OLLAMA_KV_CACHE_TYPE` and
  `OLLAMA_FLASH_ATTENTION`, including whether each is absent/defaulted;
- the effective attention/backend path if Ollama can expose it honestly;
- the exact request sampler options, chat renderer/parser, reasoning effort,
  and compaction policy.

If that audit shows that effective settings can be distinguished, run one
bounded matched screen against a retained tool-call-heavy prefix:

1. one short-context control and one late-context checkpoint;
2. identical prompt, tool schemas, model artifact, sampler, seed policy,
   hardware, and runtime build;
3. vary only one dimension, beginning with KV-cache precision if the current
   path is quantized, otherwise compare the retained `Q4_K_M` artifact with one
   higher-fidelity official artifact that fits the hardware;
4. measure structured-call validity, exact-literal custody, completion, and
   task outcome rather than treating numerical disagreement as failure;
5. use repeated samples if product sampling remains enabled; and
6. make no promotion from one workload.

Ollama does not presently give our campaign harness the full-vocabulary logits
used in the forum experiments. A matched behavioral screen is therefore the
KISS-appropriate first test. Building a logit-capture stack would be a separate
research project and is not justified by this source alone.

## Architectural Consequence

The existing empirical-model-intelligence rule should be interpreted to include
the inference engine and numerical path:

> Operational capability belongs to the complete versioned configuration:
> weights, quantization, tokenizer and chat template, sampler, context policy,
> KV-cache precision, attention/backend path, hardware topology, harness,
> skills, tools, and observed workload.

For Prime/Rook, this is a qualification and custody improvement, not a new
orchestrator. For Chirp and RookForge, a capability manifest should eventually
be able to name this runtime fingerprint when model behavior is part of the
authored capability. It should not imply that the fingerprint guarantees
semantic correctness.

## Verdict

Preserve the source and take it seriously. Its central warning fits our own
evidence: local-model behavior cannot be attributed to model weights alone.

Do not conclude that the forum author has explained our Qwen failures. Our most
important new fact is simpler: the retained campaigns used a `Q4_K_M` weight
artifact, and two potentially material runtime dimensions were not frozen.
Close that custody gap first, then run one discriminating matched screen before
changing models, Prime, Rook, or the skill strategy.
