# LM9B-P Planner Recipe Transfer Result

## Scientific Question

Can one bounded Planner session author a real
`rook.planner_graph_recipe:v1` from the governed radial brief and authority
context, without R01 or implementation leakage, and can an independently
accepted ready recipe cross unchanged into the established LM9B-C compiler
path?

The predeclared counter-hypotheses were:

1. The Planner cannot author a mechanically admissible and semantically
   faithful candidate without leakage, repair, or semantic invention.
2. An admissible and faithful model-authored candidate cannot enter the proven
   compiler unchanged and produce an accepted inert candidate.

Neither counter-hypothesis was evaluated. Provider configuration failed before
the first model turn, so no recipe existed and Checkpoint 2 was not entered.

## Preserved Attempt

```text
attempt: one canonical LM9B-P attempt
commit: 9959650ffc632c1b685db83077201fa7e503c577
checkpoint 1: probe_inconclusive
checkpoint 2: not_evaluated
aggregate: probe_inconclusive
planner attempts: 1
planner model turns: 0
planner evaluator attempts: 0
compiler attempts: 0
compiler evaluator attempts: 0
execution permitted: false
```

The immutable evidence is under:

```text
docs/superpowers/probes/lm9b-p-runs/2026-07-20-canonical/
```

It contains 33 evidence files totaling 221,255 bytes. A repository-only
`.gitattributes` transport control marks those evidence paths as byte-preserved
and is not part of either scientific seal. The canonical attempt was not rerun,
repaired, or retransmitted while preparing this report.

## Frozen Configuration

Checkpoint identity records:

```text
Planner model: gpt-5.4
Planner evaluator model: gpt-5.4
provider profile: litellm.completion.tool_calling.no_parallel:v1
Planner maximum turns: 6
Planner evaluator maximum attempts: 1
normalization profile: lm9b_p.recipe_normalization_profile:v1
normalization fingerprint:
  sha256:5b8833bd1f2554c1d91fb8f04aa71a8e7509d850ccca28036096ea24f1ac000e
```

The exact provider request additionally binds temperature `0.0`, 16,384
maximum completion tokens, a 180-second call timeout, disabled parallel tool
calls, and non-streaming behavior. Frozen source assertions at the recorded
commit also passed for the 600-second Planner deadline, 120,000-token stop
threshold, USD 10 cost threshold, and 8,192-token Planner-evaluator bound.

The committed CLI and frozen-control assertions held the compiler and compiler
evaluator at `gemini/gemini-3.1-pro-preview`, temperature `0.0`, and the
archived LM9B-C bounds. The compiler stage was not entered, so the sparse joined
archive correctly contains no compiler provider identity, request, response,
usage, or run archive. The three copied implementation-control hashes are:

```text
compiler-controls/implementation_context.json
  sha256:39cb834c2b309189104417b30defd9fb08e4d64a33f14ba22ea06925b5e22454
compiler-controls/exclusion_policy.json
  sha256:ada6b320ab8ec6a5b66d61f99f984794d0728ccb88bc44fba783dbe46e95f405
compiler-controls/evaluation_rubric.json
  sha256:a3c064f3691664bb250f565c32b77f8b8165c52192b6755c6679f88b3def6fd7
```

## Checkpoint 1 Observation

LiteLLM rejected the only Planner provider call before returning any model
response:

```text
termination: provider_failure
attempt outcome: raised
exception type: ProviderCallFailure
failure type: InternalServerError
elapsed: 1,767 ms
model turns: 0
usage evidence: none
```

The exact sanitized failure message is:

```text
litellm.InternalServerError: InternalServerError: OpenAIException - Missing credentials. Please pass an `api_key`, `workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY` or `OPENAI_ADMIN_KEY` environment variable.
```

The archive retains both the exact serialized provider request and exact
sanitized error. There is no raw response, usage record, tool submission,
mechanical recipe evaluation, final recipe, or Planner classification evidence
beyond the controller-derived `probe_inconclusive` result.

The Planner evaluator did not run. Its complete evidence is the closed
`evaluator/not_run.json` record and zero evaluator attempts.

## Checkpoint 2 Observation

Checkpoint 2 is `not_evaluated`. No final recipe existed, so there was no
handoff, recipe-byte equality proof, LM9B-C input load, rendered compiler
request, compiler provider call, compiler evaluator call, or compiler archive.

This is not a compiler failure and not a contract-insufficiency observation.

## Aggregate Classification

The mechanically sealed aggregate records:

```text
checkpoint 1: probe_inconclusive
checkpoint 2: not_evaluated
aggregate outcome: probe_inconclusive
handoff: null
LM9B-C archive: null
execution permitted: false
```

All four recipe-byte hashes are null and `all_equal` is false because no recipe
was authored. This is absence evidence, not a failed byte-equality comparison.

## Deterministic Verification

The production checkpoint verifier accepted every required file, exact file-set
closure, record role, byte length, SHA-256, capture variant, and canonical
aggregate binding against this retained identity:

```text
checkpoint aggregate identity:
  sha256:ca782b786fe9f07072e50d07264623cfd0a825a05caf6794fb78be8bf39003cd
checkpoint checksums bytes:
  sha256:fb573053ec8eb484e85b735ccf6224999b2a1cebe1a58c681884b754fed62769
```

The joined aggregate has exact two-file closure. Its single record was
recomputed from `aggregate.json`, and its identity was recomputed with the
production canonicalizer:

```text
joined aggregate identity:
  sha256:8777701ebdd7a591f4d848964459c454f46a24821cf7cd04958edcff193b0acb
joined checksums bytes:
  sha256:8c8398a8f3df4dda0a28a9d7ff99e9e30edcbe825429a8f523320b2ddbb039e2
```

The joined record binds the exact checkpoint identity above. The report also
independently confirmed the recorded Git head, model/profile identities,
frozen bounds, one raised Planner attempt, zero model turns, evaluator
non-entry, missing final recipe, missing handoff/compiler archive, and
`execution_permitted=false` at both seals.

## Key Evidence Bindings

```text
checkpoint-1/inputs/attempt_context.json
  sha256:3095edd92b875244efa9b25bc16b27bf598b4d5362fa1cec3edb5eaeafe9b3d5
checkpoint-1/inputs/manifest.json
  sha256:bd1fe552c0b2f6a915aaae7fd3e80a93aa17abc47bb0cf6fdc67969e1fa6e729
checkpoint-1/planner/request.json
  sha256:58d1aaca806cf42e1c235311d8eb977502e86b4710ca842eb96fc71af591bb73
checkpoint-1/identity.json
  sha256:ed22cf9741d49c7407ed9e481a76f8203abe7ff677ca52922549ebedc877e3be
checkpoint-1/checkpoint/session.json
  sha256:d59398bea4595eb9f80c29837213c60c1155097c5f9f26c491b8380d5d50f5e8
checkpoint-1/checkpoint/classification.json
  sha256:41529ca7cdecc2e467764c3466dddcd2cf9cf6ca9813a74584e68f7a5baca2d7
checkpoint-1/planner/attempts/000/capture.json
  sha256:40ebdadfb34988f543ab0f22180d40d8437ae5a99015c7114eb573f29d9754f8
checkpoint-1/planner/attempts/000/provider_request.json
  sha256:2e49ee9e8c535c79e5c27fde5557cbb3957bfa98548e6fcd06b9ea123977e032
checkpoint-1/planner/attempts/000/raw_request.bin
  sha256:0ea30aa9272bfc7dc470d029c2b8cc1da7855cf37a352c1c25551fe1fe2399b2
checkpoint-1/planner/attempts/000/raw_error.bin
  sha256:67b56dd43d81b6787e4e32708a2573315b47487f5da4f6ddc2f98cc723d5290b
checkpoint-1/evaluator/not_run.json
  sha256:28a37983ea005197a7febb7b94e3f435ad8449a7a61f35c8575b83ad3fcb13f3
joined-aggregate/aggregate.json
  sha256:72cc2b1d2a67b0321cea1e9ad367b7ee507009866ae30e0e24d511316c05a5a0
joined-aggregate/checksums.json
  sha256:8c8398a8f3df4dda0a28a9d7ff99e9e30edcbe825429a8f523320b2ddbb039e2
```

## Matched Historical Control

R01 comparison is not applicable because the Planner produced no final recipe.
The canonical execution path did not invoke the post-freeze comparison, and no
R01 comparison artifact exists in the archive. Step 6 did not read an R01
recipe or force an answer-key comparison.

## Scientific Conclusion

An environmental/provider configuration failure made the one canonical
attempt inconclusive. The failure occurred before any model turn, so this run
does not provide evidence for or against Planner recipe authorship. With no
accepted recipe, it also does not provide evidence for or against unchanged
joined transfer into LM9B-C.

The evidence system did preserve and classify the failure honestly: one exact
provider attempt, complete sanitized transport failure evidence, no evaluator
or compiler activity, no fabricated recipe or archive, and no execution.

## Limitations

- The provider rejected the request before model inference; no model behavior
  was observed.
- No Planner output, semantic evaluation, or downstream compilation exists to
  inspect.
- The archive captures LiteLLM's complete logical request/error objects, not
  authenticated HTTP wire bytes.
- Full compiler model identities are fixed by the committed CLI and source
  guards but are not repeated in the sparse joined aggregate because the
  compiler stage was not entered.
- This is one attempt. It provides no repeatability evidence.

## Non-Claims

This result does not establish:

- Planner success or Planner failure;
- mechanical or semantic validity of any recipe;
- honest blocked-intent behavior;
- recipe-contract sufficiency or insufficiency;
- unchanged compiler transfer;
- compiler behavior, reliability, or generality;
- product integration, execution authorization, or live runtime behavior;
- either predeclared counter-hypothesis.

## Next Falsifiable Experiment

A future experiment should use a new attempt identity, new unused run root, and
newly reviewed committed SHA after a deterministic provider-configuration
readiness gate confirms that the selected Planner profile has usable credentials
without recording secrets. It should retain the same governed semantic inputs,
non-authoritative classification boundary, no-repair rule, and conditional
unchanged LM9B-C handoff.

That new experiment can again ask whether the Planner authors an admissible,
faithful recipe and, only if ready, whether the unchanged compiler consumes it.
It is a new controlled observation, not a retry or repair of this canonical
attempt.
