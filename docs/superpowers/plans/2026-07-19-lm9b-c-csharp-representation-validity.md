# LM9B-C C# Representation Validity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the first LM9B-C run and perform one independent follow-up whose success requires the exact Rook RhinoCode C# representation contract.

**Architecture:** Add one narrow reusable full-source contract validator beside Rook's existing broad C# preflight, then bind it into the disposable probe before evaluator invocation and outcome classification. Render the legal trace-reference catalog from the same R01-derived index used by deterministic trace validation. Preserve raw evidence locally and commit only checksums and the scientific report.

**Tech Stack:** Python 3.10, pytest, existing `rook.gh_csharp_preflight`, JSON Schema, LiteLLM Gemini transport, Rook MCP Grasshopper tools.

## Global Constraints

- Do not change R01 or its authority artifacts.
- Do not edit the historical run directory or its evidence files.
- Do not write a general C# parser or change normal product body-mode behavior.
- Do not expose topology, source code, expected output, or evaluator rubric in the trace catalog.
- Run one follow-up compiler attempt only; do not repair or retry it.
- Run the live smoke only when the exact mechanical contract passes.
- Stop on any need for kernel, schema, vocabulary, generalized IR, or backend work.

---

### Task 1: Preserve And Reinterpret The Historical Run

**Files:**
- Create: `docs/superpowers/probes/2026-07-19-lm9b-c-compiler-sufficiency-result.md`
- Create: `docs/superpowers/probes/evidence/lm9b-c-20260719T073319Z-bfe46886.SHA256SUMS`
- Preserve outside Git: `C:/Users/bring/.rook/probe-archives/lm9b-c-20260719T073319Z-bfe46886/`

**Interfaces:**
- Consumes: the 38 immutable files under `probe_runs/lm9b-c-20260719T073319Z-bfe46886/`.
- Produces: a reviewed interpretation and a complete content manifest without replacing raw evidence.

- [ ] **Step 1: Generate and verify the checksum manifest in memory**

Use sorted forward-slash relative paths and exact lines:

```text
sha256:<lowercase digest>  <relative path>\n
```

Assert 38 files, 1,120,445 aggregate bytes, and manifest hash
`sha256:39bae8d4ab37c6f941c605ddc010c6641463c184cda6dab90034adc75a68a871`.

- [ ] **Step 2: Copy the raw run without mutation**

Copy every file to
`C:/Users/bring/.rook/probe-archives/lm9b-c-20260719T073319Z-bfe46886/`, then re-run the manifest against the archive and require byte-for-byte equality.

- [ ] **Step 3: Commit the report and checksum manifest**

The report must preserve the historical outcome while stating:

```text
semantic lowering demonstrated
representation validity not demonstrated
```

It must name the incorrect base type/signature, same-model evaluator limitation,
turn-one trace feedback, all key hashes, and the raw archive location.

- [ ] **Step 4: Verify and commit**

```powershell
git diff --check -- docs/superpowers/probes
git add -- docs/superpowers/probes/2026-07-19-lm9b-c-compiler-sufficiency-result.md docs/superpowers/probes/evidence/lm9b-c-20260719T073319Z-bfe46886.SHA256SUMS
git commit -m "docs(lm9b): preserve compiler probe evidence"
```

### Task 2: Add The Exact Rook Full-Source Contract Check

**Files:**
- Modify: `mcp_server/src/rook/gh_csharp_preflight.py`
- Modify: `mcp_server/tests/test_gh_csharp_preflight.py`
- Modify: `mcp_server/tests/test_lm9b_c_compiler_sufficiency_support.py`

**Interfaces:**
- Produces: `validate_rhinocode_csharp_full_source(*, code, pins_in, pins_out) -> CSharpRepresentationContractResult`.
- Preserves: `preflight_csharp_script` behavior and API.

- [ ] **Step 1: Write exact-contract failures first**

Add tests proving the preserved first candidate fails with both
`missing_gh_script_instance_base` and `runscript_signature_mismatch`. Add focused
tests for wrong visibility, missing/extra/reordered/renamed parameters,
`out object`, missing inheritance, `GH_Component`, duplicate RunScript, and exact
pin name/type/access/order binding.

- [ ] **Step 2: Prove the tests fail**

```powershell
python -m pytest mcp_server/tests/test_gh_csharp_preflight.py -q
```

Expected: failures because the exact validator is absent.

- [ ] **Step 3: Implement the narrow recognizer**

Add an immutable result containing `ok` and an ordered tuple of stable error
codes. Recognize only the known `Script_Instance` class declaration and one
`RunScript` signature. Parse the comma-separated parameter list only after the
method envelope matches; require this exact expected tuple:

```python
expected = tuple(
    [("value", "object", pin["name"]) for pin in pins_in]
    + [("ref", "object", pin["name"]) for pin in pins_out]
)
```

Do not attempt C# expression, statement, namespace, or type-system parsing.

- [ ] **Step 4: Run focused and compatibility tests**

```powershell
python -m pytest mcp_server/tests/test_gh_csharp_preflight.py mcp_server/tests/test_server_contract_hardening.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add -- mcp_server/src/rook/gh_csharp_preflight.py mcp_server/tests/test_gh_csharp_preflight.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_support.py
git commit -m "feat(lm9b): validate RhinoCode C# representation contract"
```

### Task 3: Bind Mechanical Validity And The Trace Catalog Into The Probe

**Files:**
- Modify: `scripts/lm9b_c_compiler_sufficiency_support.py`
- Modify: `scripts/lm9b_c_compiler_sufficiency_artifacts.py`
- Modify: `scripts/lm9b_c_compiler_sufficiency_probe.py`
- Modify: `scripts/lm9b_c_fixtures/implementation_context.json`
- Modify: `scripts/lm9b_c_fixtures/input_manifest.json`
- Modify: `mcp_server/tests/test_lm9b_c_compiler_sufficiency_support.py`
- Modify: `mcp_server/tests/test_lm9b_c_compiler_sufficiency_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_c_compiler_sufficiency_probe.py`

**Interfaces:**
- Consumes: unchanged R01 and authority records plus corrected generic implementation context.
- Produces: exact mechanical validation evidence and `legal_trace_reference_catalog` derived from `contract_index`.

- [ ] **Step 1: Write failing probe-integration tests**

Require:

- evaluator invocation only for a schema-valid, trace-valid, mechanically valid candidate;
- evaluator acceptance cannot override mechanical failure;
- final success requires `representation_contract_ok is True`;
- the legal catalog exactly matches the R01-derived contract index;
- the catalog contains no C# source, topology, expected solution, task example, or rubric;
- R01 and all three authority raw hashes remain unchanged.

- [ ] **Step 2: Run focused tests and observe failure**

```powershell
python -m pytest mcp_server/tests/test_lm9b_c_compiler_sufficiency_support.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_artifacts.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_probe.py -q
```

- [ ] **Step 3: Implement the minimal wiring**

Extend terminal validation evidence with exact mechanical status and codes. In
the orchestrator, do not invoke the evaluator for a mechanically invalid
candidate. Update classification so `bounded_lowering_demonstrated` requires
schema, trace, mechanical, and evaluator acceptance.

Render `legal_trace_reference_catalog` from the same `contract_index` object
used by `_validate_candidate_trace`; do not maintain a second list.

Update only `implementation_context.json` and its manifest hashes to state:

```text
Script_Instance : GH_ScriptInstance
one private void RunScript
object inputs
ref object outputs
declared pin order
out and GH_Component forbidden
```

- [ ] **Step 4: Run the complete deterministic gate**

```powershell
python -m pytest mcp_server/tests/test_gh_csharp_preflight.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_support.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_artifacts.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_probe.py -q
python -m compileall -q mcp_server/src/rook/gh_csharp_preflight.py scripts/lm9b_c_compiler_sufficiency_support.py scripts/lm9b_c_compiler_sufficiency_artifacts.py scripts/lm9b_c_compiler_sufficiency_probe.py
git diff --check
```

- [ ] **Step 5: Commit before transmission**

```powershell
git add -- mcp_server/src/rook/gh_csharp_preflight.py scripts/lm9b_c_compiler_sufficiency_support.py scripts/lm9b_c_compiler_sufficiency_artifacts.py scripts/lm9b_c_compiler_sufficiency_probe.py scripts/lm9b_c_fixtures/implementation_context.json scripts/lm9b_c_fixtures/input_manifest.json mcp_server/tests/test_gh_csharp_preflight.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_support.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_artifacts.py mcp_server/tests/test_lm9b_c_compiler_sufficiency_probe.py
git commit -m "feat(lm9b): gate compiler evidence on C# contract"
```

### Task 4: Run One Follow-Up And One Conditional Live Smoke

**Files:**
- Produce ignored evidence: `probe_runs/lm9b-c-<timestamp>-<commit>/`
- Amend report after review: `docs/superpowers/probes/2026-07-19-lm9b-c-compiler-sufficiency-result.md`

**Interfaces:**
- Consumes: the committed corrected probe and exact frozen inputs.
- Produces: one preserved compiler/evaluator observation and, conditionally, one live Grasshopper result.

- [ ] **Step 1: Run exactly one bounded attempt**

```powershell
python scripts/lm9b_c_compiler_sufficiency_probe.py --compiler-model gemini/gemini-3.1-pro-preview --evaluator-model gemini/gemini-3.1-pro-preview --run-root probe_runs
```

Do not rerun for any red or inconclusive result.

- [ ] **Step 2: Audit the run**

Verify commit identity, R01/authority hashes, turn count, mechanical result,
trace result, evaluator disposition, tokens, cost, and absence of persisted
secrets. Record exact hashes for decision, terminal, mechanical check, trace,
and evaluator report.

- [ ] **Step 3: Run the conditional live smoke**

Only for a mechanically passing candidate, create a fresh disposable
Grasshopper document and one RhinoCode C# Script component using the exact
unmodified source and declared pins. Inspect component errors and output data;
verify the 100-box geometry and radial-height equations from the design. Do not
repair a compile or runtime failure.

- [ ] **Step 4: Curate and verify**

Append the follow-up observation and any live result to the committed report.
Run focused tests, adjacent C# preflight tests, Python compile, diff checks, and
secret/domain-leak scans. Commit the exact reviewed evidence summary; leave raw
run directories ignored.
