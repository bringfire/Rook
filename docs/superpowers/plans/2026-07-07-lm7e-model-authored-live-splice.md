# LM7E Model-Authored Live Splice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic machinery for LM7E: one Planner-model-authored `intent_incomplete` request is strictly parsed, validated, materialized, and consumed by the frozen LM7B live splice path.

**Architecture:** Add a new sibling live probe script for LM7E, keeping LM7B and LM7C meanings intact. Extract the LM7C/LM7D authoring prompt/menu/brief surface into a tiny script-support helper so LM7E uses the exact shape-guidance prompt semantics, then compose LM7E from Planner provider call, strict pre-live gates, LM7A materialization, LM5AA runtime routing, LM5X/LM5W criteria assembly, and the existing one-turn worker splice.

**Tech Stack:** Python 3.10, pytest, existing Rook agent modules, existing LM7B/LM7C script helpers, direct subprocess provider-command seam, no new dependencies.

## Global Constraints

- New sibling script: `scripts/lm7e_model_authored_live_splice_probe.py`.
- Do not extend LM7B or LM7C as runtime modes.
- Canonical Planner provider/model: `codex-cli-chatgpt` / `gpt-5.5`.
- Canonical worker model remains the frozen LM6/LM7B worker default: `gemma4:12b-it-qat` through direct Ollama `/api/chat`.
- Canonical scenario is fixed: `intent_incomplete`.
- Canonical attempts are fixed: `1`.
- Prompt profile is fixed: `shape_guidance_v2`.
- Strict JSON parse only: no markdown extraction, no JSON repair, no Planner retry, no second Planner attempt.
- If Planner provider, parse, parsed-request marker, or `workflow_validate` fails, no Rhino/GH work and no worker publication may run.
- Worker retry is disabled and unavailable in LM7E v1.
- Worker prompt/evidence shape must preserve LM7B/LM6 envelope.
- Do not change LM5W/LM5X/LM5Y, LM6, LM7A schema, `workflow_validate`, or worker-action applier semantics.
- No live model, Rhino, Grasshopper, Ollama, or worker publication in implementation PR tests.
- No live run artifacts committed.
- Known unrelated local files must remain untouched: `knowledge/gh/operations_knowledge.json`, `.understand-anything/`, and Rook2 draft docs.

---

## File Structure

Create:

- `scripts/lm7_planner_authoring_prompt_support.py`
  Script-support helper for the exact LM7C/LM7D prompt/menu/brief/parser/intent-classifier primitives. It owns pure authoring artifacts and strict request parsing, not LM7C row scoring or LM7E live splice.

- `scripts/lm7e_model_authored_live_splice_probe.py`
  New LM7E sibling probe. It owns Planner provider call, raw output provenance, strict gates, materialization artifacts, LM7B-style live splice composition, and LM7E decision records.

- `mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py`
  Deterministic tests using fake Planner provider and fake live/worker seams only.

Modify:

- `scripts/lm7c_planner_authoring_probe.py`
  Delegate prompt/menu/brief/parser/classifier helpers to `lm7_planner_authoring_prompt_support.py` while preserving existing private helper names and output behavior.

- `mcp_server/tests/test_lm7c_planner_authoring_probe.py`
  Add preservation tests proving sparse and shape-guidance prompt artifacts remain byte-for-byte unchanged after extraction.

Do not modify:

- `mcp_server/src/rook/**/*.py`
- `scripts/lm7b_request_driven_live_splice_probe.py`
- `scripts/lm6a_live_worker_splice_probe.py`
- `scripts/lm_worker_two_pass_publication.py`
- LM5/LM6/LM7A validator, extractor, assembler, applier modules

---

### Task 1: Extract Planner Authoring Prompt Support

**Files:**
- Create: `scripts/lm7_planner_authoring_prompt_support.py`
- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

**Interfaces:**
- Produces:
  - `PROBE_SCHEMA: str`
  - `PROMPT_PROFILE_SPARSE_V1: str`
  - `PROMPT_PROFILE_SHAPE_GUIDANCE_V2: str`
  - `PROMPT_PROFILES: tuple[str, str]`
  - `SPARSE_PROMPT_VERSION: str`
  - `SHAPE_GUIDANCE_PROMPT_VERSION: str`
  - `TEMPLATE_MENU_VERSION: str`
  - `INTENT_COMPLETE_BRIEF_VERSION: str`
  - `INTENT_INCOMPLETE_BRIEF_VERSION: str`
  - `SCENARIOS: tuple[str, str]`
  - `ParseResult`
  - `IntentDecisionResult`
  - `planner_authoring_prompt(prompt_profile: str = PROMPT_PROFILE_SPARSE_V1) -> str`
  - `prompt_version(prompt_profile: str) -> str`
  - `template_menu() -> dict[str, Any]`
  - `scenario_brief(scenario: str) -> dict[str, str]`
  - `prompt_call_payload(*, scenario: str, attempt_index: int, provider: str, model: str, temperature: float, prompt_profile: str) -> dict[str, Any]`
  - `write_prompt_artifacts(run_dir: Path, prompt_profile: str, scenarios: Sequence[str] = SCENARIOS) -> None`
  - `strict_parse_model_output(raw_output: str) -> ParseResult`
  - `classify_intent_decision(scenario: str, payload: Mapping[str, Any]) -> IntentDecisionResult`
  - `canonical_json(value: Any) -> str`
  - `fingerprint_json(value: Mapping[str, Any] | Sequence[Any] | str) -> str`
- Consumes:
  - constants from `rook.agent.planner_worker_contract_request`
- Later tasks rely on:
  - LM7E importing prompt/profile/brief/parser/classifier helpers without importing LM7C row scoring or run logic.

- [ ] **Step 1: Write failing LM7C preservation tests**

Append these tests to `mcp_server/tests/test_lm7c_planner_authoring_probe.py`:

```python
def test_prompt_support_payload_preserves_lm7c_probe_schema() -> None:
    import importlib.util

    helper_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7_planner_authoring_prompt_support.py"
    )
    spec = importlib.util.spec_from_file_location(
        "lm7_planner_authoring_prompt_support_schema_test",
        helper_path,
    )
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)

    payload = helper.prompt_call_payload(
        scenario="intent_incomplete",
        attempt_index=0,
        provider="codex-cli-chatgpt",
        model="gpt-5.5",
        temperature=0,
        prompt_profile="shape_guidance_v2",
    )

    assert helper.PROBE_SCHEMA == "rook.lm7c_planner_authoring_probe:v1"
    assert payload["schema"] == helper.PROBE_SCHEMA
    assert payload["schema"] == PROBE.PROBE_SCHEMA


def test_prompt_support_helper_matches_lm7c_sparse_artifacts(tmp_path: Path) -> None:
    import importlib.util

    helper_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7_planner_authoring_prompt_support.py"
    )
    spec = importlib.util.spec_from_file_location(
        "lm7_planner_authoring_prompt_support_for_test",
        helper_path,
    )
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)

    assert helper.planner_authoring_prompt("sparse_v1") == (
        PROBE._planner_authoring_prompt("sparse_v1")
    )
    assert helper.prompt_version("sparse_v1") == PROBE._prompt_version("sparse_v1")
    assert helper.template_menu() == PROBE._template_menu()
    assert helper.scenario_brief("intent_complete") == (
        PROBE._scenario_brief("intent_complete")
    )
    assert helper.scenario_brief("intent_incomplete") == (
        PROBE._scenario_brief("intent_incomplete")
    )


def test_prompt_support_helper_matches_lm7c_shape_guidance_artifacts() -> None:
    import importlib.util

    helper_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7_planner_authoring_prompt_support.py"
    )
    spec = importlib.util.spec_from_file_location(
        "lm7_planner_authoring_prompt_support_for_shape_test",
        helper_path,
    )
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)

    assert helper.planner_authoring_prompt("shape_guidance_v2") == (
        PROBE._planner_authoring_prompt("shape_guidance_v2")
    )
    assert helper.prompt_version("shape_guidance_v2") == (
        PROBE._prompt_version("shape_guidance_v2")
    )
```

- [ ] **Step 2: Run tests to verify helper is missing**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_support_helper_matches_lm7c_sparse_artifacts `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_support_helper_matches_lm7c_shape_guidance_artifacts `
  -q
```

Expected: FAIL with missing `scripts/lm7_planner_authoring_prompt_support.py`.

- [ ] **Step 3: Create support helper**

Create `scripts/lm7_planner_authoring_prompt_support.py` by moving the pure prompt/menu/brief/parser/classifier code from `scripts/lm7c_planner_authoring_probe.py`.

The file must start with:

```python
#!/usr/bin/env python
"""Shared LM7 Planner authoring prompt/parser support."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

from rook.agent.planner_worker_contract_request import (  # noqa: E402
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    MISSING_DESIRED_OUTPUT_ROUTE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
)
```

The helper must define these constants exactly:

```python
PROBE_SCHEMA = "rook.lm7c_planner_authoring_probe:v1"
PROMPT_PROFILE_SPARSE_V1 = "sparse_v1"
PROMPT_PROFILE_SHAPE_GUIDANCE_V2 = "shape_guidance_v2"
PROMPT_PROFILES = (
    PROMPT_PROFILE_SPARSE_V1,
    PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
)

SPARSE_PROMPT_VERSION = "lm7c.planner_authoring_prompt:v1"
SHAPE_GUIDANCE_PROMPT_VERSION = "lm7d.planner_authoring_prompt_shape_guidance:v2"
PLANNER_AUTHORING_PROMPT_VERSION = SPARSE_PROMPT_VERSION
TEMPLATE_MENU_VERSION = "lm7c.template_menu:v1"
INTENT_COMPLETE_BRIEF_VERSION = "lm7c.intent_complete_brief:v1"
INTENT_INCOMPLETE_BRIEF_VERSION = "lm7c.intent_incomplete_brief:v1"
SCENARIOS = ("intent_complete", "intent_incomplete")

PARSE_PARSED = "parsed"
PARSE_FAILED = "parse_failed"

INTENT_CORRECT = "correct_declared"
INTENT_OVER_DECLARED = "over_declared"
INTENT_INVENTED = "invented"
INTENT_NOT_CLASSIFIABLE = "not_classifiable"
```

Move `ParseResult`, `IntentDecisionResult`, `_sparse_planner_authoring_prompt`,
`_shape_guidance_planner_authoring_prompt`, `_template_menu`, `_scenario_brief`,
`_prompt_call_payload`, `_prompt_version`, `_write_prompt_artifacts`,
`_strict_parse_model_output`, `_canonical_unresolved_slot_present`,
`_canonical_unresolved_route_present`, `_mapping_sequence`,
`_has_extra_unresolved_intent`, `_contains_invented_concrete_intent`,
`_contains_repair_code_field`, `_classify_intent_decision`,
`_canonical_json`, and `_fingerprint_json` from LM7C into this helper.

Rename public helper functions by removing the leading underscore:

```python
def planner_authoring_prompt(prompt_profile: str = PROMPT_PROFILE_SPARSE_V1) -> str
def template_menu() -> dict[str, Any]
def scenario_brief(scenario: str) -> dict[str, str]
def prompt_call_payload(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    prompt_profile: str,
) -> dict[str, Any]
def prompt_version(prompt_profile: str) -> str
def write_prompt_artifacts(
    run_dir: Path,
    prompt_profile: str,
    scenarios: Sequence[str] = SCENARIOS,
) -> None
def strict_parse_model_output(raw_output: str) -> ParseResult
def classify_intent_decision(
    scenario: str,
    payload: Mapping[str, Any],
) -> IntentDecisionResult
def canonical_json(value: Any) -> str
def fingerprint_json(value: Mapping[str, Any] | Sequence[Any] | str) -> str
```

`write_prompt_artifacts` must write the same filenames LM7C currently writes:

```python
def write_prompt_artifacts(
    run_dir: Path,
    prompt_profile: str,
    scenarios: Sequence[str] = SCENARIOS,
) -> None:
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "planner_authoring_prompt.txt").write_text(
        planner_authoring_prompt(prompt_profile) + "\n",
        encoding="utf-8",
    )
    (prompts_dir / "template_menu.json").write_text(
        json.dumps(template_menu(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    for scenario in scenarios:
        brief = scenario_brief(scenario)
        (prompts_dir / f"{scenario}_brief.txt").write_text(
            f"version: {brief['version']}\n\n{brief['text']}\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Modify LM7C to delegate without changing its interface**

In `scripts/lm7c_planner_authoring_probe.py`, import the helper:

```python
from lm7_planner_authoring_prompt_support import (  # noqa: E402
    PROBE_SCHEMA,
    INTENT_COMPLETE_BRIEF_VERSION,
    INTENT_INCOMPLETE_BRIEF_VERSION,
    INTENT_CORRECT,
    INTENT_INVENTED,
    INTENT_NOT_CLASSIFIABLE,
    INTENT_OVER_DECLARED,
    PARSE_FAILED,
    PARSE_PARSED,
    PLANNER_AUTHORING_PROMPT_VERSION,
    PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
    PROMPT_PROFILE_SPARSE_V1,
    PROMPT_PROFILES,
    SCENARIOS,
    SHAPE_GUIDANCE_PROMPT_VERSION,
    SPARSE_PROMPT_VERSION,
    TEMPLATE_MENU_VERSION,
    IntentDecisionResult,
    ParseResult,
    canonical_json as _canonical_json,
    classify_intent_decision as _classify_intent_decision,
    fingerprint_json as _fingerprint_json,
    planner_authoring_prompt as _planner_authoring_prompt,
    prompt_call_payload as _prompt_call_payload,
    prompt_version as _prompt_version,
    scenario_brief as _scenario_brief,
    strict_parse_model_output as _strict_parse_model_output,
    template_menu as _template_menu,
    write_prompt_artifacts as _write_prompt_artifacts,
)
```

Delete the duplicated LM7C definitions that moved into the helper. Keep LM7C row scoring, summary generation, provider-command execution, CLI, and `_run_probe` in `lm7c_planner_authoring_probe.py`. LM7C must still expose `PROBE_SCHEMA` at module scope by importing it from the helper, and `prompt_call_payload` must continue to emit `"schema": "rook.lm7c_planner_authoring_probe:v1"`.

- [ ] **Step 5: Run LM7C tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  -q
```

Expected: PASS.

- [ ] **Step 6: Compile support and LM7C scripts**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm7_planner_authoring_prompt_support.py `
  scripts\lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py
```

Expected: exit 0.

---

### Task 2: LM7E Pre-Live Planner Authoring Gates

**Files:**
- Create: `scripts/lm7e_model_authored_live_splice_probe.py`
- Create: `mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py`

**Interfaces:**
- Consumes:
  - prompt support helper from Task 1
  - `validate_planner_worker_contract_request`
- Produces:
  - `_args(argv: list[str] | None) -> argparse.Namespace`
  - `_call_provider_command(command: str, call_payload: Mapping[str, Any], timeout_s: float) -> str`
  - `_run_probe` returning `Path`
  - `_decision_record` returning `dict[str, Any]`
  - `_parsed_request_has_planner_markers(payload: Mapping[str, Any]) -> bool`
  - run artifacts for parse failure, marker failure, and workflow validate failure.
- Later tasks rely on:
  - `_run_probe` stopping before live work for provider, parse, marker, and validation failures.

- [ ] **Step 1: Write failing test loader and CLI tests**

Create `mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py` with:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rook.agent.planner_worker_contract_request import (
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    materialize_planner_worker_contract_request,
)
from rook.agent.local_worker_source_routing_validator import (
    SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
    SourceRoutingDiagnostic,
    WorkerVisibleSourceRoutingValidationReport,
)


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7e_model_authored_live_splice_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm7e_model_authored_live_splice_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def _valid_incomplete_request() -> dict[str, object]:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": "repair_same_component_from_create_error",
        "initial_params": {"create_script": {"pins_out": ["A:double"]}},
        "routing_delta": {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [
                {
                    "route_id": "missing_desired_output_value",
                    "source_class": "planner_user_intent",
                    "source_path": "planner.intent.desired_output_value",
                    "purpose": "unresolved_intent",
                    "required": False,
                }
            ],
        },
        "intent_slots": [
            {
                "intent_id": "desired_output_value",
                "status": "unresolved",
                "source_path": "planner.intent.desired_output_value",
                "description": "Desired output value was not provided.",
            }
        ],
    }


def _valid_runtime_routing_report() -> WorkerVisibleSourceRoutingValidationReport:
    return WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=True,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(),
    )


def _invalid_runtime_routing_report() -> WorkerVisibleSourceRoutingValidationReport:
    diagnostic = SourceRoutingDiagnostic(
        severity="error",
        code="required_route_unresolved",
        node_id="repair_same_component",
        route_id="repair_target_diagnostics",
        source_class="receipt_diagnostic",
        source_path=(
            "create_script.receipt.script_receipt.repair_anchor.target_errors"
        ),
        purpose="acceptance_criteria",
        message="target diagnostics did not resolve",
    )
    return WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=False,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(diagnostic,),
    )


def _real_live_for_lm7e() -> dict[str, object]:
    from rook.agent.plan_graph_workflow_contract import compile_workflow_contract
    from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step

    materialization = materialize_planner_worker_contract_request(
        _valid_incomplete_request()
    )
    contract = PROBE.load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    scaffold = compile_workflow_contract(contract)
    graph = scaffold.graph
    graph.nodes["create_script"].metadata["execution_params"] = dict(
        contract.initial_params[0].execution_params
    )
    producer_result = apply_producer_result(
        graph,
        "create_script",
        {
            "success": False,
            "message": "Component created with compile errors.",
            "data": {
                "script_receipt": {
                    "version": 1,
                    "operation": "create",
                    "language": "csharp",
                    "artifact_status": "created_with_errors",
                    "mutation": {
                        "status": "created",
                        "component_guid": "component-1",
                    },
                    "verification": {
                        "status": "failed",
                        "target_error_count": 1,
                    },
                    "repair_anchor": {
                        "component_guid": "component-1",
                        "language": "csharp",
                        "target_errors": [
                            "The name 'DefinitelyMissingSymbol' does not exist."
                        ],
                    },
                },
            },
        },
    )
    graph = producer_result.graph
    verify_create = apply_verifier_step(graph, "verify_create", "create_script")
    graph = verify_create.graph
    return {
        "workflow_contract": contract,
        "scaffold": scaffold,
        "graph": graph,
        "convention_packets": (PROBE._script_body_gotcha_packet(),),
        "anchor_binding": {"component_guid": "component-1", "language": "csharp"},
        "live_create_summary": {
            "node_id": "create_script",
            "repair_anchor": {
                "component_guid": "component-1",
                "language": "csharp",
                "target_errors": [
                    "The name 'DefinitelyMissingSymbol' does not exist."
                ],
            },
        },
        "verify_create_summary": {"verifier_node_id": "verify_create"},
    }


def test_cli_defaults_split_planner_and_worker_models() -> None:
    args = PROBE._args(["--planner-provider-command", "fake-provider"])

    assert args.planner_provider_command == "fake-provider"
    assert args.planner_provider == "codex-cli-chatgpt"
    assert args.planner_model == "gpt-5.5"
    assert args.worker_model == "gemma4:12b-it-qat"
    assert args.worker_endpoint == "http://localhost:11434/api/chat"
    assert args.worker_temperature == 0
    assert args.worker_timeout_s == 120
    assert args.output_excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is False


def test_cli_rejects_forbidden_scenario_attempt_and_retry_options() -> None:
    for option in (
        "--request-json",
        "--scenario",
        "--attempts",
        "--retry-clean-observation",
        "--phase",
        "--prompt-profile",
    ):
        with pytest.raises(SystemExit):
            PROBE._args([option, "x"])
```

- [ ] **Step 2: Run tests to verify script is missing**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py::test_cli_defaults_split_planner_and_worker_models `
  -q
```

Expected: FAIL with missing `scripts/lm7e_model_authored_live_splice_probe.py`.

- [ ] **Step 3: Create LM7E script scaffold**

Create `scripts/lm7e_model_authored_live_splice_probe.py` with imports and constants:

```python
#!/usr/bin/env python
"""LM7E model-authored request-driven live splice probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from lm6a_live_worker_splice_probe import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_EXCERPT_CHARS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_S,
)
from lm7_planner_authoring_prompt_support import (  # noqa: E402
    INTENT_CORRECT,
    INTENT_INCOMPLETE_BRIEF_VERSION,
    INTENT_NOT_CLASSIFIABLE,
    PARSE_FAILED,
    PARSE_PARSED,
    PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
    SHAPE_GUIDANCE_PROMPT_VERSION,
    TEMPLATE_MENU_VERSION,
    classify_intent_decision,
    fingerprint_json,
    prompt_call_payload,
    strict_parse_model_output,
    write_prompt_artifacts,
)
from rook.agent.workflow_validate import (  # noqa: E402
    validate_planner_worker_contract_request,
)


SCRIPT_SCHEMA = "rook.lm7e_model_authored_live_splice_probe:v1"
DECISION_SCHEMA = "rook.lm7e_decision:v1"
CANONICAL_PLANNER_PROVIDER = "codex-cli-chatgpt"
CANONICAL_PLANNER_MODEL = "gpt-5.5"
CANONICAL_SCENARIO = "intent_incomplete"
CANONICAL_ATTEMPTS = 1
HIDDEN_MARKER_SCAN_TERMS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "A = 0.0",
    "A = 1.0",
    "BindStepSpec.base_params",
    "repair_same_component.bind.base_params",
)
DECISIONS = {
    "accepted",
    "rejected",
    "worker_declined",
    "gate_failed",
    "publication_failed",
    "rejected_by_validate",
}
```

Add `_args`:

```python
def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM7E model-authored request-driven live splice probe."
    )
    parser.add_argument("--planner-provider-command", required=True)
    parser.add_argument("--planner-provider", default=CANONICAL_PLANNER_PROVIDER)
    parser.add_argument("--planner-provider-timeout-s", type=float, default=120)
    parser.add_argument("--planner-model", default=CANONICAL_PLANNER_MODEL)
    parser.add_argument("--worker-model", default=DEFAULT_MODEL)
    parser.add_argument("--worker-endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--worker-temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--worker-timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--run-dir", default="probe_runs")
    parser.add_argument("--output-excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--canonical-evidence", action="store_true")
    args = parser.parse_args(argv)
    if args.output_excerpt_chars < 0:
        parser.error("output_excerpt_chars_must_be_non_negative")
    return args
```

- [ ] **Step 4: Add pre-live helper functions**

Add these functions:

```python
def _git_short_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _new_run_dir(run_root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(run_root) / f"lm7e-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_json_value(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _excerpt(value: str, chars: int) -> str:
    return value[:chars]


def _contains_marker_text(value: str) -> bool:
    return any(marker in value for marker in HIDDEN_MARKER_SCAN_TERMS)


def _contains_marker_value(value: Any) -> bool:
    rendered = json.dumps(value, sort_keys=True, default=str)
    return _contains_marker_text(rendered)
```

Add canonical evidence validation:

```python
def _canonical_evidence_is_valid(args: argparse.Namespace) -> bool:
    if not args.canonical_evidence:
        return True
    return (
        args.planner_provider == CANONICAL_PLANNER_PROVIDER
        and args.planner_model == CANONICAL_PLANNER_MODEL
        and args.worker_model == DEFAULT_MODEL
        and args.worker_endpoint == DEFAULT_ENDPOINT
        and args.worker_temperature == DEFAULT_TEMPERATURE
    )
```

Add provider command function:

```python
def _call_provider_command(
    command: str,
    call_payload: Mapping[str, Any],
    timeout_s: float,
) -> str:
    result = subprocess.run(
        command,
        input=json.dumps(dict(call_payload), sort_keys=True),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        shell=True,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout
```

- [ ] **Step 5: Add decision and manifest helpers**

Add:

```python
def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    planner_parse_status: str,
    planner_validation_status: str,
    planner_intent_decision: str,
    planner_model_output_sha256: str | None,
    planner_model_output_excerpt: str | None,
    planner_model_output_path: str | None,
    request_fingerprint: str | None,
    workflow_validate_valid: bool | None,
    workflow_validate_report_fingerprint: str | None,
    live_rhino_work_started: bool,
    worker_publication_ran: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"Unsupported LM7E decision: {decision}")
    record = {
        "schema": DECISION_SCHEMA,
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "planner_parse_status": planner_parse_status,
        "planner_validation_status": planner_validation_status,
        "planner_intent_decision": planner_intent_decision,
        "planner_model_output_sha256": planner_model_output_sha256,
        "planner_model_output_excerpt": planner_model_output_excerpt,
        "planner_model_output_path": planner_model_output_path,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_valid": workflow_validate_valid,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "live_rhino_work_started": live_rhino_work_started,
        "worker_publication_ran": worker_publication_ran,
        "worker_retry_enabled": False,
        "live_repair_dispatched": False,
        "verify_repair_ran": False,
    }
    if extra:
        record.update(dict(extra))
    return record
```

Add:

```python
def _manifest(
    *,
    planner_provider: str,
    planner_model: str,
    worker_model: str,
    worker_endpoint: str,
    worker_temperature: float,
    canonical_evidence: bool,
    planner_model_output_sha256: str | None,
    request_fingerprint: str | None,
    workflow_validate_report_fingerprint: str | None,
    workflow_contract_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "planner_provider": planner_provider,
        "planner_model": planner_model,
        "worker_model": worker_model,
        "worker_endpoint": worker_endpoint,
        "worker_temperature": worker_temperature,
        "canonical_evidence": canonical_evidence,
        "scenario": CANONICAL_SCENARIO,
        "attempts": CANONICAL_ATTEMPTS,
        "prompt_profile": PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
        "prompt_version": SHAPE_GUIDANCE_PROMPT_VERSION,
        "template_menu_version": TEMPLATE_MENU_VERSION,
        "brief_version": INTENT_INCOMPLETE_BRIEF_VERSION,
        "worker_retry_enabled": False,
        "planner_model_output_path": "planner_model_output.txt",
        "planner_model_output_sha256": planner_model_output_sha256,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "workflow_contract_fingerprint": workflow_contract_fingerprint,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }
```

- [ ] **Step 6: Add pre-live `_run_probe` skeleton**

Add `_run_probe` that writes prompt artifacts, calls provider, writes raw output, parses, marker-gates, validates, and ends with a temporary `NotImplementedError` after successful validation. Task 3 replaces that temporary stop with materialization.

```python
def _run_probe(
    *,
    planner_provider: str,
    planner_model: str,
    planner_provider_command: str,
    planner_provider_timeout_s: float,
    worker_model: str,
    worker_endpoint: str,
    worker_temperature: float,
    worker_timeout_s: float,
    output_excerpt_chars: int,
    run_root: str | Path,
    canonical_evidence: bool,
    call_provider: Callable[[Mapping[str, Any]], str] | None = None,
    agent: Any | None = None,
) -> Path:
    run_dir = _new_run_dir(run_root)
    write_prompt_artifacts(
        run_dir,
        PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
        scenarios=(CANONICAL_SCENARIO,),
    )
    call_payload = prompt_call_payload(
        scenario=CANONICAL_SCENARIO,
        attempt_index=0,
        provider=planner_provider,
        model=planner_model,
        temperature=0,
        prompt_profile=PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
    )
    provider = call_provider or (
        lambda payload: _call_provider_command(
            planner_provider_command,
            payload,
            planner_provider_timeout_s,
        )
    )
    try:
        raw_output = provider(call_payload)
    except Exception as exc:
        raw_output = ""
        output_sha = fingerprint_json(raw_output)
        _write_text(run_dir / "planner_model_output.txt", raw_output)
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=None,
                workflow_validate_report_fingerprint=None,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason=f"planner_provider_failed:{type(exc).__name__}",
                phase="planner_provider",
                planner_parse_status=PARSE_FAILED,
                planner_validation_status="not_evaluated",
                planner_intent_decision=INTENT_NOT_CLASSIFIABLE,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt="",
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=None,
                workflow_validate_valid=None,
                workflow_validate_report_fingerprint=None,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    output_sha = fingerprint_json(raw_output)
    _write_text(run_dir / "planner_model_output.txt", raw_output)
    output_excerpt = _excerpt(raw_output, output_excerpt_chars)

    parsed = strict_parse_model_output(raw_output)
    if parsed.parse_status != PARSE_PARSED or parsed.payload is None:
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=None,
                workflow_validate_report_fingerprint=None,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason="planner_parse_failed",
                phase="planner_parse",
                planner_parse_status=PARSE_FAILED,
                planner_validation_status="not_evaluated",
                planner_intent_decision=INTENT_NOT_CLASSIFIABLE,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=None,
                workflow_validate_valid=None,
                workflow_validate_report_fingerprint=None,
                live_rhino_work_started=False,
                worker_publication_ran=False,
                extra={"planner_parse_failure_reason": parsed.failure_reason},
            ),
        )
        return run_dir

    planner_request = parsed.payload
    _write_json_value(run_dir / "planner_request.json", planner_request)
    request_fingerprint = fingerprint_json(planner_request)
    intent = classify_intent_decision(CANONICAL_SCENARIO, planner_request)

    if _contains_marker_value(planner_request):
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=request_fingerprint,
                workflow_validate_report_fingerprint=None,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason="planner_hidden_marker_detected",
                phase="planner_request_marker_gate",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="not_evaluated",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=None,
                workflow_validate_report_fingerprint=None,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    report = validate_planner_worker_contract_request(planner_request)
    _write_json_value(run_dir / "workflow_validate_report.json", report)
    workflow_validate_report_fingerprint = (
        report.get("report_fingerprint") or fingerprint_json(report)
    )
    workflow_validate_valid = report.get("valid") is True
    if not workflow_validate_valid:
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=request_fingerprint,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason="workflow_validate_failed",
                phase="workflow_validate",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_failed",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=False,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    # Task 3 continues from here.
    raise NotImplementedError("LM7E materialized live splice not implemented yet")
```

- [ ] **Step 7: Add `main`**

Add:

```python
def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if not _canonical_evidence_is_valid(args):
        print("invalid_canonical_evidence", file=sys.stderr)
        raise SystemExit(2)
    run_dir = _run_probe(
        planner_provider=args.planner_provider,
        planner_model=args.planner_model,
        planner_provider_command=args.planner_provider_command,
        planner_provider_timeout_s=args.planner_provider_timeout_s,
        worker_model=args.worker_model,
        worker_endpoint=args.worker_endpoint,
        worker_temperature=args.worker_temperature,
        worker_timeout_s=args.worker_timeout_s,
        output_excerpt_chars=args.output_excerpt_chars,
        run_root=args.run_dir,
        canonical_evidence=args.canonical_evidence,
    )
    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    print(
        "LM7E model-authored live splice probe complete "
        f"run_dir={run_dir} "
        f"decision={decision.get('decision')} "
        f"reason={decision.get('reason')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Add pre-live gate tests**

Add these tests to `mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py`:

```python
def test_parse_failure_writes_raw_output_and_no_request_or_live(tmp_path: Path) -> None:
    live_called = False

    def fake_provider(_payload):
        return "```json\n{}\n```"

    def fake_live(*_args, **_kwargs):
        nonlocal live_called
        live_called = True

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=20,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=fake_provider,
        agent=fake_live,
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "planner_model_output.txt").exists()
    assert not (run_dir / "planner_request.json").exists()
    assert not (run_dir / "workflow_validate_report.json").exists()
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "planner_parse_failed"
    assert decision["live_rhino_work_started"] is False
    assert decision["worker_publication_ran"] is False
    assert live_called is False


def test_parsed_request_marker_fails_before_workflow_validate_and_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validate_called = False

    request = _valid_incomplete_request()
    request["extra"] = "A = 0.0"

    def fake_validate(_request):
        nonlocal validate_called
        validate_called = True
        return {"valid": True}

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(request),
        agent=object(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "planner_request.json").exists()
    assert not (run_dir / "workflow_validate_report.json").exists()
    assert validate_called is False
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "planner_hidden_marker_detected"
    assert decision["planner_parse_status"] == "parsed"
    assert decision["planner_validation_status"] == "not_evaluated"
```

Add workflow validate failure test:

```python
def test_workflow_validate_failure_stops_before_materialization_and_live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialize_called = False

    def fake_validate(_request):
        return {
            "valid": False,
            "request_fingerprint": "sha256:req",
            "report_fingerprint": "sha256:report",
        }

    def fake_materialize(_request):
        nonlocal materialize_called
        materialize_called = True

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        fake_materialize,
        raising=False,
    )

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert (run_dir / "planner_request.json").exists()
    assert (run_dir / "workflow_validate_report.json").exists()
    assert materialize_called is False
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "workflow_validate_failed"
    assert decision["workflow_validate_valid"] is False
```

- [ ] **Step 9: Run pre-live tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py `
  -q
```

Expected: tests written so far pass, except tests for materialization/live not yet present.

---

### Task 3: Materialization, Routing Artifact, and Contract Summary

**Files:**
- Modify: `scripts/lm7e_model_authored_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py`

**Interfaces:**
- Consumes:
  - `_run_probe` from Task 2
  - `materialize_planner_worker_contract_request(payload: Mapping[str, Any])`
  - `load_workflow_contract_payload(workflow_contract_payload: Mapping[str, Any])`
- Produces:
  - `_workflow_contract_summary(template_id: str, workflow_contract_payload: Mapping[str, Any], workflow_contract: Any, worker_node_ids: Sequence[str]) -> dict[str, Any]`
  - `_workflow_contract_summary_fingerprint(summary: Mapping[str, Any]) -> str`
  - full `resolved_source_routing.json`
  - bounded `workflow_contract_summary.json`
- Later tasks rely on:
  - materialized workflow contract and routing artifact passed to live sequence.

- [ ] **Step 1: Add failing materialization artifact tests**

Append:

```python
def test_valid_request_writes_resolved_routing_and_bounded_contract_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_live_not_implemented(**_kwargs):
        raise NotImplementedError("stop before live")

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live_not_implemented, raising=False)

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )

    routing = json.loads((run_dir / "resolved_source_routing.json").read_text())
    summary = json.loads((run_dir / "workflow_contract_summary.json").read_text())
    decision = json.loads((run_dir / "decision.json").read_text())

    rendered_routing = json.dumps(routing, sort_keys=True)
    assert "missing_desired_output_value" in rendered_routing
    assert "planner.intent.desired_output_value" in rendered_routing
    assert summary["template_id"] == "repair_same_component_from_create_error"
    assert "repair_same_component" in summary["worker_node_ids"]
    assert summary["worker_node_bind_steps"]["repair_same_component"] is False
    rendered_summary = json.dumps(summary, sort_keys=True)
    for marker in (
        "base_params",
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "A = 0.0",
        "A = 1.0",
    ):
        assert marker not in rendered_summary
    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_not_implemented"


def test_workflow_contract_summary_reports_worker_bind_step_presence_without_base_params() -> None:
    payload = {
        "initial_params": [],
        "rules": [
            {
                "node_id": "repair_same_component",
                "steps_by_seen_count": [
                    {
                        "kind": "bind",
                        "node_id": "repair_same_component",
                        "base_params": {"code": "PROBE_REPAIR_CODE"},
                        "bindings": {},
                    }
                ],
            }
        ],
        "expected_refs": [{"node_id": "repair_same_component"}],
    }
    loaded_contract = SimpleNamespace(
        initial_params=(),
        rules=(
            SimpleNamespace(
                node_id="repair_same_component",
                steps_by_seen_count=(
                    SimpleNamespace(
                        kind="bind",
                        node_id="repair_same_component",
                        base_params={"code": "PROBE_REPAIR_CODE"},
                    ),
                ),
            ),
        ),
    )

    summary = PROBE._workflow_contract_summary(
        template_id="repair_same_component_from_create_error",
        workflow_contract_payload=payload,
        workflow_contract=loaded_contract,
        worker_node_ids=("repair_same_component",),
    )

    rendered = json.dumps(summary, sort_keys=True)
    assert summary["worker_node_bind_steps"]["repair_same_component"] is True
    assert "base_params" not in rendered
    assert "PROBE_REPAIR_CODE" not in rendered
```

- [ ] **Step 2: Run test to verify missing artifacts**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py::test_valid_request_writes_resolved_routing_and_bounded_contract_summary `
  -q
```

Expected: FAIL because materialization artifacts are not implemented yet.

- [ ] **Step 3: Import materialization/contract loader**

Add to `scripts/lm7e_model_authored_live_splice_probe.py`:

```python
from rook.agent.plan_graph_workflow_contract import (  # noqa: E402
    BindStepSpec,
    load_workflow_contract_payload,
)
from rook.agent.planner_worker_contract_request import (  # noqa: E402
    materialize_planner_worker_contract_request,
)
```

- [ ] **Step 4: Add summary helpers**

Add:

```python
def _value_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            "type": "mapping",
            "keys": sorted(str(key) for key in value.keys()),
            "sha256": fingerprint_json(value),
        }
    if isinstance(value, (list, tuple)):
        return {
            "type": "sequence",
            "count": len(value),
            "sha256": fingerprint_json(list(value)),
        }
    return {
        "type": type(value).__name__,
        "sha256": fingerprint_json(str(value)),
    }


def _worker_node_bind_step_presence(
    *,
    workflow_contract_payload: Mapping[str, Any],
    workflow_contract: Any,
    worker_node_ids: Sequence[str],
) -> dict[str, bool]:
    presence = {str(node_id): False for node_id in worker_node_ids}
    for rule in workflow_contract_payload.get("rules", ()):
        if not isinstance(rule, Mapping):
            continue
        node_id = str(rule.get("node_id") or "")
        if node_id not in presence:
            continue
        for step in rule.get("steps_by_seen_count", ()):
            if isinstance(step, Mapping) and step.get("kind") == "bind":
                presence[node_id] = True
    for rule in getattr(workflow_contract, "rules", ()):
        node_id = str(getattr(rule, "node_id", ""))
        if node_id not in presence:
            continue
        for step in getattr(rule, "steps_by_seen_count", ()):
            if isinstance(step, BindStepSpec) or getattr(step, "kind", None) == "bind":
                presence[node_id] = True
    return presence


def _workflow_contract_summary(
    *,
    template_id: str,
    workflow_contract_payload: Mapping[str, Any],
    workflow_contract: Any,
    worker_node_ids: Sequence[str],
) -> dict[str, Any]:
    node_ids: set[str] = set()
    rule_ids: list[str] = []
    initial_param_summary: dict[str, Any] = {}

    for initial in workflow_contract_payload.get("initial_params", ()):
        if isinstance(initial, Mapping):
            node_id = str(initial.get("node_id") or "")
            if node_id:
                node_ids.add(node_id)

    for rule in workflow_contract_payload.get("rules", ()):
        if isinstance(rule, Mapping):
            node_id = str(rule.get("node_id") or "")
            if node_id:
                node_ids.add(node_id)

    for expected_ref in workflow_contract_payload.get("expected_refs", ()):
        if isinstance(expected_ref, Mapping):
            node_id = str(expected_ref.get("node_id") or "")
            if node_id:
                node_ids.add(node_id)

    for initial in getattr(workflow_contract, "initial_params", ()):
        node_id = str(getattr(initial, "node_id", ""))
        if node_id:
            node_ids.add(node_id)
            initial_param_summary[node_id] = {
                str(key): _value_shape(value)
                for key, value in getattr(initial, "execution_params", {}).items()
            }

    for rule in getattr(workflow_contract, "rules", ()):
        node_id = str(getattr(rule, "node_id", ""))
        if node_id:
            rule_ids.append(node_id)

    worker_node_bind_steps = _worker_node_bind_step_presence(
        workflow_contract_payload=workflow_contract_payload,
        workflow_contract=workflow_contract,
        worker_node_ids=worker_node_ids,
    )
    return {
        "schema": "rook.lm7e_workflow_contract_summary:v1",
        "template_id": template_id,
        "node_ids": sorted(node_ids),
        "rule_ids": sorted(rule_ids),
        "worker_node_ids": list(worker_node_ids),
        "worker_node_bind_steps": worker_node_bind_steps,
        "initial_param_summary": initial_param_summary,
    }
```

- [ ] **Step 5: Extend `_run_probe` after workflow_validate success**

Replace the `raise NotImplementedError("LM7E live splice not implemented until Task 3")` at the end of Task 2 with:

```python
    materialization = materialize_planner_worker_contract_request(planner_request)
    workflow_contract = load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    resolved_routing = materialization.resolved_routing_artifact
    worker_node_ids = tuple(materialization.worker_node_ids)
    _write_json_value(run_dir / "resolved_source_routing.json", resolved_routing)
    contract_summary = _workflow_contract_summary(
        template_id=str(planner_request.get("template_id")),
        workflow_contract_payload=materialization.workflow_contract_payload,
        workflow_contract=workflow_contract,
        worker_node_ids=worker_node_ids,
    )
    if _contains_marker_value(contract_summary):
        raise RuntimeError("workflow_contract_summary_hidden_marker")
    _write_json_value(run_dir / "workflow_contract_summary.json", contract_summary)
    workflow_contract_fingerprint = fingerprint_json(contract_summary)
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            planner_provider=planner_provider,
            planner_model=planner_model,
            worker_model=worker_model,
            worker_endpoint=worker_endpoint,
            worker_temperature=worker_temperature,
            canonical_evidence=canonical_evidence,
            planner_model_output_sha256=output_sha,
            request_fingerprint=request_fingerprint,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
            workflow_contract_fingerprint=workflow_contract_fingerprint,
        ),
    )
```

Then call the Task 4 live seam stub:

```python
    try:
        live_result = _run_live_create_and_verify(
            agent=agent,
            workflow_contract=workflow_contract,
        )
    except NotImplementedError:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="runtime_not_implemented",
                phase="runtime_live_create",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir
```

- [ ] **Step 6: Add `_run_live_create_and_verify` stub**

Add:

```python
def _run_live_create_and_verify(*, agent: Any, workflow_contract: Any) -> dict[str, Any]:
    raise NotImplementedError("LM7E live create/verify is implemented in Task 4.")
```

- [ ] **Step 7: Run materialization tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py `
  -q
```

Expected: PASS for pre-live and materialization tests.

---

### Task 4: LM7B-Style Live Splice Consumption

**Files:**
- Modify: `scripts/lm7e_model_authored_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py`

**Interfaces:**
- Consumes:
  - materialized `workflow_contract`
  - `resolved_routing`
  - `planner_request`
  - LM7B helper functions that are already parameterized
- Produces:
  - runtime routing gate
  - LM5X/LM5W acceptance criteria artifacts
  - worker publication/action/live repair decisions
- Later tasks rely on:
  - complete deterministic fake accepted/declined/failure coverage.

- [ ] **Step 1: Add imports from LM7B and LM6A helpers**

In `scripts/lm7e_model_authored_live_splice_probe.py`, import only neutral helpers:

```python
from lm6a_live_worker_splice_probe import (  # noqa: E402
    _decision_from_worker_action_apply,
    _decision_from_worker_publication,
    _dispatch_repair_and_verify,
    _hidden_answer_leaks,
    _pass1_decision_hidden_answer_failure,
    _routing_report_json,
    _worker_action_context,
)
from lm7b_request_driven_live_splice_probe import (  # noqa: E402
    _acceptance_source_contract,
    _build_agent,
    _build_worker_context,
    _is_materialized_live_result,
    _report_fingerprint,
    _routing_report_has_errors,
    _run_live_create_and_verify,
    _script_body_gotcha_packet,
)
from lm_worker_two_pass_publication import run_two_pass_worker_publication  # noqa: E402
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
)
from rook.agent.plan_graph_worker_action_apply import (  # noqa: E402
    apply_worker_action_to_node,
)
```

Do not import or call these LM7B/LM6A non-neutral helpers:

```text
_canonical_planner_request
_worker_request_payload
_acceptance_criteria_evidence_packet
```

- [ ] **Step 2: Add static guard test for forbidden helper calls**

Append:

```python
def test_static_guard_forbids_hand_authored_request_and_non_neutral_worker_helpers() -> None:
    source = _script_path().read_text(encoding="utf-8")
    forbidden = [
        "_canonical_planner_request",
        "_worker_request_payload",
        "_acceptance_criteria_evidence_packet",
        "script_local_canonical_lm7a_request",
        "lm6e_bounded_retry_context",
        "retry_clean_observation",
    ]

    for marker in forbidden:
        assert marker not in source
```

- [ ] **Step 3: Add fake live accepted-path test**

Use the local `_real_live_for_lm7e()` helper from Task 2. Do not import fixtures from `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`; LM7E tests must remain self-contained.

Add accepted-path test:

```python
def test_fake_live_action_request_reaches_accepted_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = _real_live_for_lm7e()
    captured_worker_kwargs = []
    captured_routing_contracts = []

    class FakePublication:
        row = {"status": "published"}
        response_payload = {
            "kind": "action_request",
            "action_id": "draft_repair_params",
            "input": {"code": "A = 0.0;", "mode": "body"},
        }

    def fake_live_create(**_kwargs):
        return live

    def fake_validate_routing(*_args, **kwargs):
        captured_routing_contracts.append(kwargs["workflow_contract"])
        return _valid_runtime_routing_report()

    def fake_publication(payload, **kwargs):
        captured_worker_kwargs.append(kwargs)
        return FakePublication()

    def fake_apply(graph, node_id, *, action_id, action_input, anchor_binding, **_kwargs):
        class Result:
            applied = True
            reason = None
            params_sha256 = "sha256:params"
            graph = live["graph"]
        return Result()

    def fake_dispatch(**_kwargs):
        return {
            "decision": {
                "schema": "rook.lm6a_decision:v1",
                "decision": "accepted",
                "reason": "verify_repair_succeeded",
                "phase": "verify_repair",
                "live_repair_dispatched": True,
                "verify_repair_ran": True,
            }
        }

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live_create)
    monkeypatch.setattr(PROBE, "validate_worker_visible_source_routing", fake_validate_routing)
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)
    monkeypatch.setattr(PROBE, "apply_worker_action_to_node", fake_apply)
    monkeypatch.setattr(PROBE, "_dispatch_repair_and_verify", fake_dispatch)

    run_dir = PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_repair_succeeded"
    assert decision["worker_publication_ran"] is True
    assert decision["live_rhino_work_started"] is True
    assert decision["planner_validation_status"] == "workflow_validate_valid"
    assert (run_dir / "runtime_routing_validation.json").exists()
    assert (run_dir / "acceptance_criteria_packet.json").exists()
    assert (run_dir / "worker_visible_acceptance_criteria.json").exists()
    assert (run_dir / "worker_publication_row.json").exists()
    assert (run_dir / "worker_action.json").exists()
    assert captured_worker_kwargs[0]["model"] == "gemma4:12b-it-qat"
    assert captured_worker_kwargs[0]["endpoint"] == "http://localhost:11434/api/chat"
    assert captured_worker_kwargs[0]["temperature"] == 0
    routing_contract = captured_routing_contracts[0]
    create_initial = next(
        item for item in routing_contract.initial_params if item.node_id == "create_script"
    )
    assert create_initial.execution_params["pins_out"] == ["A:double"]
    assert isinstance(create_initial.execution_params["pins_out"], list)
```

- [ ] **Step 4: Implement runtime/live continuation**

After Task 3 materialization, continue `_run_probe` with:

```python
    live_result = _run_live_create_and_verify(
        agent=agent,
        workflow_contract=workflow_contract,
    )
    if not (isinstance(live_result, Mapping) and _is_materialized_live_result(live_result)):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="live_create_result_invalid",
                phase="live_create",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=True,
                worker_publication_ran=False,
            ),
        )
        return run_dir
```

Use LM7B's result enrichment:

```python
    live_result = dict(live_result)
    live_result["resolved_routing_artifact"] = resolved_routing
    live_result["planner_request"] = planner_request
```

Write:

```python
_write_json(run_dir / "live_create_summary.json", live_result["live_create_summary"])
_write_json(run_dir / "verify_create_summary.json", live_result["verify_create_summary"])
```

Run runtime routing:

```python
    routing_report = validate_worker_visible_source_routing(
        resolved_routing,
        workflow_contract=_acceptance_source_contract(live_result["workflow_contract"]),
        graph=live_result["graph"],
        convention_packets=live_result["convention_packets"],
        worker_node_ids=tuple(worker_node_ids),
    )
    _write_json(run_dir / "runtime_routing_validation.json", _routing_report_json(routing_report))
```

Gate:

```python
    runtime_routing_valid = routing_report.valid if isinstance(routing_report.valid, bool) else None
    runtime_routability_evaluated = routing_report.routability_evaluated is True
    if not runtime_routability_evaluated:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="runtime_routability_not_evaluated",
                phase="runtime_routing",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=True,
                worker_publication_ran=False,
                extra={
                    "runtime_routing_valid": runtime_routing_valid,
                    "runtime_routability_evaluated": runtime_routability_evaluated,
                },
            ),
        )
        return run_dir
    elif _routing_report_has_errors(routing_report):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="runtime_routability_failed",
                phase="runtime_routing",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=True,
                worker_publication_ran=False,
                extra={
                    "runtime_routing_valid": runtime_routing_valid,
                    "runtime_routability_evaluated": runtime_routability_evaluated,
                },
            ),
        )
        return run_dir
```

Build worker request with LM7B `_build_worker_context(live=live_result, run_dir=run_dir)`:

```python
    request_payload = _build_worker_context(live=live_result, run_dir=run_dir)
```

This is allowed because it uses the passed `live["planner_request"]`, `live["workflow_contract"]`, and `live["resolved_routing_artifact"]`, and it writes LM5W artifact-only + legacy worker-visible projection.

Run one-turn publication:

```python
publication = run_two_pass_worker_publication(
    request_payload,
    model=worker_model,
    endpoint=worker_endpoint,
    temperature=worker_temperature,
    timeout_s=worker_timeout_s,
    excerpt_chars=output_excerpt_chars,
    decision_guard=_pass1_decision_hidden_answer_failure,
)
```

Preserve LM7B hidden-answer behavior:

```python
if _hidden_answer_leaks(publication.row) or _hidden_answer_leaks(publication.response_payload):
    _write_json(
        run_dir / "decision.json",
        _decision_record(
            decision="publication_failed",
            reason="worker_publication_hidden_answer_leak",
            phase="worker_publication",
            planner_parse_status=PARSE_PARSED,
            planner_validation_status="workflow_validate_valid",
            planner_intent_decision=intent.intent_decision,
            planner_model_output_sha256=output_sha,
            planner_model_output_excerpt=output_excerpt,
            planner_model_output_path="planner_model_output.txt",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
            live_rhino_work_started=True,
            worker_publication_ran=True,
        ),
    )
    return run_dir
```

Write final row only after hidden-answer check passes:

```python
_write_json(run_dir / "worker_publication_row.json", publication.row)
```

Use `_decision_from_worker_publication(publication_row=publication.row, response_payload=publication.response_payload)` for non-action terminal classification, then rewrap the result in LM7E metadata:

```python
worker_decision = _decision_from_worker_publication(
    publication_row=publication.row,
    response_payload=publication.response_payload,
)
if worker_decision is not None:
    _write_json(
        run_dir / "decision.json",
        _decision_record(
            decision=str(worker_decision["decision"]),
            reason=str(worker_decision["reason"]),
            phase=str(worker_decision["phase"]),
            planner_parse_status=PARSE_PARSED,
            planner_validation_status="workflow_validate_valid",
            planner_intent_decision=intent.intent_decision,
            planner_model_output_sha256=output_sha,
            planner_model_output_excerpt=output_excerpt,
            planner_model_output_path="planner_model_output.txt",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
            live_rhino_work_started=True,
            worker_publication_ran=True,
            extra={
                key: value
                for key, value in worker_decision.items()
                if key not in {"schema", "decision", "reason", "phase"}
            },
        ),
    )
    return run_dir
```

For action:

```python
response_payload = publication.response_payload
action_context = _worker_action_context(
    response_payload=response_payload,
    run_dir=run_dir,
    excerpt_chars=output_excerpt_chars,
)
_write_json(run_dir / "worker_action.json", response_payload)
apply_result = apply_worker_action_to_node(
    live_result["graph"],
    "repair_same_component",
    action_id=str(response_payload.get("action_id") or ""),
    action_input=response_payload.get("input"),
    anchor_binding=live_result["anchor_binding"],
)
```

Use `_decision_from_worker_action_apply(apply_result, action_context=action_context)` for applier rejection and `_dispatch_repair_and_verify(graph=apply_result.graph, agent=agent, params_sha256=apply_result.params_sha256, run_dir=run_dir, action_context=action_context)` for live repair + verify result. Both return LM6A-shaped decisions; rewrap them with `_decision_record` using the same pattern as worker publication above. For successful action apply:

```python
if apply_result.applied is not True:
    worker_decision = _decision_from_worker_action_apply(
        apply_result,
        action_context=action_context,
    )
    _write_json(
        run_dir / "decision.json",
        _decision_record(
            decision=str(worker_decision["decision"]),
            reason=str(worker_decision["reason"]),
            phase=str(worker_decision["phase"]),
            planner_parse_status=PARSE_PARSED,
            planner_validation_status="workflow_validate_valid",
            planner_intent_decision=intent.intent_decision,
            planner_model_output_sha256=output_sha,
            planner_model_output_excerpt=output_excerpt,
            planner_model_output_path="planner_model_output.txt",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
            live_rhino_work_started=True,
            worker_publication_ran=True,
            extra={
                key: value
                for key, value in worker_decision.items()
                if key not in {"schema", "decision", "reason", "phase"}
            },
        ),
    )
    return run_dir

repair_result = _dispatch_repair_and_verify(
    graph=apply_result.graph,
    agent=agent,
    params_sha256=apply_result.params_sha256,
    run_dir=run_dir,
    action_context=action_context,
)
worker_decision = repair_result["decision"]
_write_json(
    run_dir / "decision.json",
    _decision_record(
        decision=str(worker_decision["decision"]),
        reason=str(worker_decision["reason"]),
        phase=str(worker_decision["phase"]),
        planner_parse_status=PARSE_PARSED,
        planner_validation_status="workflow_validate_valid",
        planner_intent_decision=intent.intent_decision,
        planner_model_output_sha256=output_sha,
        planner_model_output_excerpt=output_excerpt,
        planner_model_output_path="planner_model_output.txt",
        request_fingerprint=request_fingerprint,
        workflow_validate_valid=True,
        workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
        live_rhino_work_started=True,
        worker_publication_ran=True,
        extra={
            key: value
            for key, value in worker_decision.items()
            if key not in {"schema", "decision", "reason", "phase"}
        },
    ),
)
return run_dir
```

Every terminal decision must be wrapped in LM7E metadata through `_decision_record`, not LM7B's schema.

- [ ] **Step 5: Add routing/decline/failure tests**

Add:

```python
def _run_valid_lm7e_with_live_fakes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    routing_report: WorkerVisibleSourceRoutingValidationReport | None = None,
    publication: object | None = None,
    apply_result: object | None = None,
) -> Path:
    live = _real_live_for_lm7e()

    if routing_report is None:
        routing_report = _valid_runtime_routing_report()

    if publication is None:
        class DefaultPublication:
            row = {"status": "published"}
            response_payload = {
                "kind": "action_request",
                "action_id": "draft_repair_params",
                "input": {"code": "A = 0.0;", "mode": "body"},
            }
        publication = DefaultPublication()

    if apply_result is None:
        class DefaultApplyResult:
            applied = True
            reason = None
            params_sha256 = "sha256:params"
            graph = live["graph"]
        apply_result = DefaultApplyResult()

    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", lambda **_kwargs: live)
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *_args, **_kwargs: routing_report,
    )
    monkeypatch.setattr(
        PROBE,
        "run_two_pass_worker_publication",
        lambda *_args, **_kwargs: publication,
    )
    monkeypatch.setattr(
        PROBE,
        "apply_worker_action_to_node",
        lambda *_args, **_kwargs: apply_result,
    )
    monkeypatch.setattr(
        PROBE,
        "_dispatch_repair_and_verify",
        lambda **_kwargs: {
            "decision": {
                "schema": "rook.lm6a_decision:v1",
                "decision": "accepted",
                "reason": "verify_repair_succeeded",
                "phase": "verify_repair",
                "live_repair_dispatched": True,
                "verify_repair_ran": True,
            }
        },
    )

    return PROBE._run_probe(
        planner_provider="codex-cli-chatgpt",
        planner_model="gpt-5.5",
        planner_provider_command="unused",
        planner_provider_timeout_s=1,
        worker_model="gemma4:12b-it-qat",
        worker_endpoint="http://localhost:11434/api/chat",
        worker_temperature=0,
        worker_timeout_s=120,
        output_excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        call_provider=lambda _payload: json.dumps(_valid_incomplete_request()),
        agent=object(),
    )


def _assert_valid_planner_metadata(decision: dict[str, object]) -> None:
    assert decision["worker_retry_enabled"] is False
    assert decision["planner_parse_status"] == "parsed"
    assert decision["planner_validation_status"] == "workflow_validate_valid"
    assert isinstance(decision["request_fingerprint"], str)
    assert isinstance(decision["workflow_validate_report_fingerprint"], str)


def test_runtime_routing_error_writes_gate_failed_without_worker_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        routing_report=_invalid_runtime_routing_report(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_routability_failed"
    assert decision["worker_publication_ran"] is False
    assert (run_dir / "runtime_routing_validation.json").exists()
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)


def test_worker_observation_decline_reuses_worker_declined_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ObservationPublication:
        row = {"status": "published", "observation_action_intent_anomaly": False}
        response_payload = {"kind": "observation", "message": "I cannot act."}

    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        publication=ObservationPublication(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed"
    assert decision["worker_publication_ran"] is True
    assert not (run_dir / "worker_publication_rows.json").exists()
    assert not (run_dir / "retry_context.json").exists()
    assert not (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)


def test_worker_publication_hidden_answer_leak_writes_publication_failed_without_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LeakingPublication:
        row = {"status": "published", "debug": "PROBE_REPAIR_CODE"}
        response_payload = {"kind": "observation", "message": "no action"}

    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        publication=LeakingPublication(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_hidden_answer_leak"
    assert decision["worker_publication_ran"] is True
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)


def test_worker_action_apply_rejection_writes_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectApplyResult:
        applied = False
        reason = "invalid_mode"
        params_sha256 = None
        graph = object()

    run_dir = _run_valid_lm7e_with_live_fakes(
        tmp_path,
        monkeypatch,
        apply_result=RejectApplyResult(),
    )

    decision = json.loads((run_dir / "decision.json").read_text())

    assert decision["decision"] == "rejected"
    assert decision["reason"] == "worker_action_apply_failed:invalid_mode"
    assert decision["worker_publication_ran"] is True
    assert decision["live_repair_dispatched"] is False
    assert decision["verify_repair_ran"] is False
    assert (run_dir / "worker_publication_row.json").exists()
    assert (run_dir / "worker_action.json").exists()
    _assert_valid_planner_metadata(decision)
```

- [ ] **Step 6: Run LM7E tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py `
  -q
```

Expected: PASS.

---

### Task 5: Static Guards, Full Nearby Gate, and Diff Scope

**Files:**
- Modify: `mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

**Interfaces:**
- Consumes:
  - final LM7E script and support helper
- Produces:
  - static import/marker/scope guards
  - documented verification commands for PR readiness

- [ ] **Step 1: Add static boundary guard tests**

In `test_lm7e_model_authored_live_splice_probe.py`, add:

```python
def test_static_guard_no_live_prompt_or_protocol_drift() -> None:
    source = _script_path().read_text(encoding="utf-8")
    forbidden = [
        "lm6e_bounded_retry_context",
        "--retry-clean-observation",
        "worker_publication_rows.json",
        "_canonical_planner_request",
        "script_local_canonical_lm7a_request",
        "_worker_request_payload",
        "_acceptance_criteria_evidence_packet",
        "PROBE_REPAIR_CODE =",
        "A = 42.0;",
    ]

    for marker in forbidden:
        assert marker not in source


def test_planner_marker_scan_excludes_worker_action_fields() -> None:
    decision = {
        "worker_action_input_excerpt": "A = 0.0;",
        "worker_action_input_sha256": "sha256:abc",
        "planner_model_output_excerpt": "{}",
    }

    assert PROBE._planner_marker_matches_in_metadata(decision) == []
```

Implement `_planner_marker_matches_in_metadata(value: Any) -> list[str]` as a pure helper that walks mappings/lists/scalars and skips mapping keys beginning with:

```text
worker_action_input_
```

and skips:

```text
worker_action.json
```

It must scan Planner prompt artifacts, `planner_model_output_excerpt`, `planner_request.json`, `resolved_source_routing.json`, and `workflow_contract_summary.json`, but it must not treat legitimate worker-authored action code in `worker_action_input_excerpt` or `worker_action.json` as a Planner marker match.

- [ ] **Step 2: Add prompt parity artifact tests**

In `test_lm7e_model_authored_live_splice_probe.py`, add:

```python
def test_lm7e_prompt_artifacts_match_lm7d_shape_guidance(tmp_path: Path) -> None:
    PROBE.write_prompt_artifacts(
        tmp_path,
        PROBE.PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
        scenarios=("intent_incomplete",),
    )

    prompt = (tmp_path / "prompts" / "planner_authoring_prompt.txt").read_text()
    menu = (tmp_path / "prompts" / "template_menu.json").read_text()
    brief = (tmp_path / "prompts" / "intent_incomplete_brief.txt").read_text()

    assert "lm7d.planner_authoring_prompt_shape_guidance:v2" in prompt
    assert '"route_id": "missing_desired_output_value"' in prompt
    assert '"source_path": "planner.intent.desired_output_value"' in prompt
    assert "lm7c.template_menu:v1" in menu
    assert "lm7c.intent_incomplete_brief:v1" in brief
    for marker in ("PROBE_REPAIR_CODE", "A = 42.0", "A = 0.0", "A = 1.0"):
        assert marker not in prompt
        assert marker not in menu
        assert marker not in brief
```

- [ ] **Step 3: Compile scripts and tests**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm7_planner_authoring_prompt_support.py `
  scripts\lm7c_planner_authoring_probe.py `
  scripts\lm7e_model_authored_live_splice_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py
```

Expected: exit 0.

- [ ] **Step 4: Run focused and nearby tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Verify exact diff scope**

Run:

```powershell
$expected = @(
  "docs/superpowers/specs/2026-07-07-lm7e-model-authored-live-splice-design.md",
  "docs/superpowers/plans/2026-07-07-lm7e-model-authored-live-splice.md",
  "scripts/lm7_planner_authoring_prompt_support.py",
  "scripts/lm7c_planner_authoring_probe.py",
  "scripts/lm7e_model_authored_live_splice_probe.py",
  "mcp_server/tests/test_lm7c_planner_authoring_probe.py",
  "mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py"
)
$actual = git diff --name-only main..HEAD
Compare-Object $expected $actual
```

Expected: no output.

- [ ] **Step 6: Run whitespace check**

Run:

```powershell
git diff --check main..HEAD
```

Expected: clean.

- [ ] **Step 7: Run forbidden production drift check**

Run:

```powershell
git diff --name-only main..HEAD | Select-String `
  -Pattern "^mcp_server/src/rook/"
```

Expected: no output.

Run:

```powershell
git diff --name-only main..HEAD | Select-String `
  -Pattern "lm6a_live_worker_splice_probe.py|lm7b_request_driven_live_splice_probe.py|lm_worker_two_pass_publication.py"
```

Expected: no output, unless the implementation review explicitly approved a helper extraction that touched LM7B. The default plan does not touch those files.

- [ ] **Step 8: Commit**

Commit after all verification passes:

```powershell
git add `
  docs\superpowers\plans\2026-07-07-lm7e-model-authored-live-splice.md `
  scripts\lm7_planner_authoring_prompt_support.py `
  scripts\lm7c_planner_authoring_probe.py `
  scripts\lm7e_model_authored_live_splice_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py

git commit -m "Implement LM7E model-authored live splice probe"
```

---

## Final Verification Before PR

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q

py -3.10 -m py_compile `
  scripts\lm7_planner_authoring_prompt_support.py `
  scripts\lm7c_planner_authoring_probe.py `
  scripts\lm7e_model_authored_live_splice_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7e_model_authored_live_splice_probe.py

git diff --check main..HEAD
```

Expected:

```text
pytest: all selected tests pass
py_compile: exit 0
git diff --check main..HEAD: clean
```

No live LM7E run is allowed in the implementation PR. The post-merge canonical run happens only after the deterministic PR merges and `main` is synced.
