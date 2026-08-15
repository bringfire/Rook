# Empirical Model Intelligence

**Status:** Rook guiding principle and working note for *Coordinating Intelligence: Lessons Learned While Building Rook*

**Date:** 2026-08-14

## Principle

A trained model is not a conventional software component whose capabilities are
fully specified by its architecture, training recipe, benchmark scores, model
card, or developers. Its useful and unreliable behaviors must be discovered
empirically through controlled interaction.

The weights are not a capability specification.

Researchers can know the architecture, training process, data mixture,
aggregate evaluations, and intended operating envelope without possessing a
complete predictive map of:

- what concepts and procedures became encoded;
- what is absent, distorted, or only weakly represented;
- which prompts or environments will elicit a latent capability;
- which forms of deliberation will improve, suppress, or displace it;
- how the model will behave when tools, errors, partial state, and long context
  enter the loop; or
- whether an observed success will repeat under nearby conditions.

This is not a claim that model developers know nothing. It is a claim that no
one receives a complete behavioral specification merely by training or
possessing the model. The model remains a partially observed system.

## Capability Is Contextual

"Does the model know this?" is usually not a well-formed engineering question.
An unsuccessful result can mean very different things:

- the relevant knowledge is absent from the weights;
- the knowledge is present but was not elicited;
- the model recognized the right answer but could not construct it;
- the model constructed something plausible but could not verify it;
- deliberation displaced a correct prior with a confident confabulation;
- the interface hid or distorted authoritative information;
- the runtime amplified an early mistake; or
- the evidence was insufficient to distinguish failure from success.

Likewise, a successful result may reveal a strategy, abstraction, or repair
ability that was never explicitly designed, anticipated, or benchmarked.

Competence is therefore an observed interaction among at least:

```text
model
+ task
+ elicitation
+ reasoning policy
+ grounding
+ tools and schemas
+ runtime loop
+ acceptance evidence
```

Changing any one of these can reveal a different apparent intelligence.

## Three Observation Layers

Rook should distinguish three layers rather than collapsing them into one
notion of model quality.

### 1. Raw capability

Ask the model directly, without Rook, Prime, or tool use. This probes recalled
domain knowledge, semantic understanding, planning, verification ideas, and
epistemic discipline.

### 2. Grounded capability

Provide authoritative component identities, schemas, metadata, or other
evidence while leaving the model responsible for reasoning. This reveals which
raw failures were knowledge or retrieval failures rather than reasoning
failures.

### 3. Operational capability

Place the model inside the real agent and tool environment. Observe discovery,
calls, mutations, recovery, cost, latency, completion claims, and mechanically
verified outcomes. This measures the coordinated system, not the model in
isolation.

These layers answer different questions. A failure at one layer does not prove
failure at the others.

## The Empirical Method

Rook development should treat model integration partly as experimental science
and systems identification:

1. Interrogate a candidate model directly with small representative problems.
2. Preserve the exact question, settings, response, reasoning trace when
   available, latency, and token observations.
3. Change one meaningful variable at a time.
4. Repeat the question across models and operating policies.
5. Introduce authoritative grounding and observe what changes.
6. Test the model in the authentic runtime with trustworthy state evidence.
7. Attribute failures to the narrowest supported owner: knowledge, elicitation,
   interface, runtime, execution, verification, or model judgment.
8. Build only the coordination infrastructure justified by repeated evidence.
9. Rerun unchanged probes after each correction.
10. Keep every model capability profile provisional and version-specific.

Model self-reports are useful hypotheses, not authoritative evidence. A single
probe is an observation, not a complete characterization. Repetition and varied
task specimens remain necessary without requiring an imaginary exhaustive
benchmark.

## What Determinism Owns

Deterministic machinery should not attempt to enumerate intelligence or every
valid solution. Its role is narrower and more important: establish what
actually happened.

For Rook, this includes authoritative schemas, strict admission, authentic
mutation receipts, solve-fenced snapshots, diagnostics, perturbation evidence,
and explicit `pass`, `fail`, or `unproven` outcomes.

```text
nondeterministic intelligence
-> proposes, explores, interprets, and repairs

deterministic evidence
-> establishes state, causality, and acceptance claims
```

The deterministic boundary lets uncertain intelligence reveal itself without
allowing confident narration to substitute for execution. It should remain an
evidence substrate, not become an infinite catalog of anticipated solutions.

## Motivating Observation

On 2026-08-14, informal direct Ollama CLI probes asked fresh conversations of
Qwen3.6:35b and Nemotron 3.5 Lightning 30B the same concise Grasshopper
point-row question. Only the model and reasoning setting changed.

| Model | Setting | Duration | Generated tokens | Observed result |
|---|---:|---:|---:|---|
| Qwen3.6:35b | low | 21.6s | 3,076 | Canonical one-Series topology |
| Qwen3.6:35b | medium | 38.0s | 5,018 | Incorrectly recalled the Series contract |
| Qwen3.6:35b | high | 86.6s | 15,606 | Denied Series existed and devised a geometric workaround |
| Nemotron 3.5 Lightning 30B | low | 33.7s | 6,771 | Correct but overbuilt three-Series topology |
| Nemotron 3.5 Lightning 30B | medium | 29.4s | 2,526 | Correct index-Series arithmetic topology |
| Nemotron 3.5 Lightning 30B | high | 14.1s | 2,216 | Canonical one-Series topology |

These are single-sample probes, not benchmark results. They do not establish a
universal ordering of models or reasoning settings. Their significance is that
an apparently obvious assumption failed: increasing deliberation did not have
a consistent direction of effect across the two models. It worsened Qwen's
answer while improving Nemotron's answer, and more reasoning did not
necessarily consume more tokens.

The reasoning-level result is only a demonstration of the larger principle. We
did not know in advance how either trained system would respond, and intuition
would have selected the wrong policy for at least one of them.

## Implications for Rook

Rook should coordinate observed intelligences rather than an imagined generic
model.

- Supported models need evidence-backed, versioned operating profiles.
- Reasoning policy, grounding, tool presentation, and repair authority may be
  model-specific and task-sensitive.
- Direct probes should precede expensive runtime redesign.
- Authoritative host metadata should supply facts that additional deliberation
  cannot reliably manufacture.
- Runtime traces and deterministic acceptance should separate interface defects
  from model defects.
- The system should permit escalation, grounding, critique, or repair based on
  observed failure evidence rather than applying maximum intelligence
  everywhere.
- New infrastructure should answer a demonstrated need across specimens, not
  encode one model's accidental behavior as universal architecture.

This posture does not abandon the goal of broad model support. It replaces
unsupported universality with progressive empirical generalization.

## Barcelona Dialogue

The deeper lesson for *Coordinating Intelligence* is that coordination does not
begin with allocating work among known agents. It begins with discovering the
shape of intelligences that are only partially known, including by their own
creators.

The practical thesis is:

> Interrogate each intelligence, observe it under progressively richer
> conditions, build the minimum infrastructure its demonstrated boundaries
> justify, and use deterministic evidence to keep every claim honest.

Intelligence is not a scalar resource that behaves predictably when given more
time, context, tools, or permission. Coordinating it requires curiosity before
confidence, experiments before architecture, and evidence before claims.
