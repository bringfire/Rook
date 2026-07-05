# LM5W Acceptance-Criteria Assembly Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure deterministic acceptance-criteria assembly boundary that reproduces the LM5U-winning criteria section with provenance and fingerprinting.

**Architecture:** Create one new `rook.agent.local_worker_acceptance_criteria` module with frozen typed source containers and a single assembler function. The assembler accepts already-selected source facts, emits the exact six LM5U v1 criteria in deterministic order, and returns a fresh versioned packet with source index, unresolved-intent list, and SHA-256 fingerprint. Probe scripts remain runtime-unchanged; tests compare the new boundary to the existing LM5U fixture through a legacy projection.

**Tech Stack:** Python 3.10, stdlib `dataclasses`, `json`, `hashlib`, pytest, existing LM5K probe fixture helpers for reproduction tests only.

---

## File Structure

Create:

```text
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
mcp_server/tests/test_local_worker_acceptance_criteria.py
```

Already created:

```text
docs/superpowers/specs/2026-07-05-lm5w-acceptance-criteria-assembly-boundary-design.md
docs/superpowers/plans/2026-07-05-lm5w-acceptance-criteria-assembly-boundary.md
```

Do not modify:

```text
mcp_server/src/rook/agent/__init__.py
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
```

Important boundaries:

- No package-level re-export.
- No Planner, Compiler, graph, scaffold, receipt, probe-script, model, transport, parser, or file IO imports in the new module.
- The new module may use stdlib `json` only for canonical fingerprinting.
- LM5W v1 is intentionally strict and fixture-shaped. Do not generalize arbitrary pins or diagnostics.

---

### Task 1: Public Surface And Canonical Packet

**Files:**
- Create: `mcp_server/tests/test_local_worker_acceptance_criteria.py`
- Create: `mcp_server/src/rook/agent/local_worker_acceptance_criteria.py`

- [ ] **Step 1: Write the failing public-surface and canonical-packet tests**

Create `mcp_server/tests/test_local_worker_acceptance_criteria.py` with:

```python
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

from rook.agent.local_worker_acceptance_criteria import (
    ACCEPTANCE_CRITERIA_PACKET_SCHEMA,
    AcceptanceCriteriaSource,
    AcceptanceCriteriaSources,
    UnresolvedIntentEntry,
    assemble_acceptance_criteria_packet,
)


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = (
    "workflow_contract.rules.verify_repair.expected_outcome"
)
DIAGNOSTIC_SOURCE_PATH = (
    "create_script.receipt.script_receipt.repair_anchor.target_errors"
)
CONVENTION_SOURCE_PATH = "script_body_gotcha"
TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' "
    "does not exist in the current context."
)


def _valid_sources(**overrides):
    values = {
        "pin_contract": AcceptanceCriteriaSource(
            source_class="pin_contract",
            source_path=PIN_SOURCE_PATH,
            value={"pins_out": ["A:double"]},
        ),
        "verifier_outcome": AcceptanceCriteriaSource(
            source_class="verifier_outcome",
            source_path=VERIFY_SOURCE_PATH,
            value="succeeded",
        ),
        "receipt_diagnostic": AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[TARGET_DIAGNOSTIC],
        ),
        "convention": AcceptanceCriteriaSource(
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
            value={"mode": "body"},
        ),
        "unresolved_intent": (),
    }
    values.update(overrides)
    return AcceptanceCriteriaSources(**values)


def _without_fingerprint(packet):
    return {key: value for key, value in packet.items() if key != "fingerprint"}


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_acceptance_criteria as module

    assert module.__all__ == (
        "ACCEPTANCE_CRITERIA_PACKET_SCHEMA",
        "AcceptanceCriteriaSource",
        "UnresolvedIntentEntry",
        "AcceptanceCriteriaSources",
        "assemble_acceptance_criteria_packet",
    )
    assert (
        ACCEPTANCE_CRITERIA_PACKET_SCHEMA
        == "rook.acceptance_criteria_packet:v1"
    )


def test_assemble_canonical_lm5u_acceptance_criteria_packet() -> None:
    packet = assemble_acceptance_criteria_packet(_valid_sources())

    assert packet["schema"] == ACCEPTANCE_CRITERIA_PACKET_SCHEMA
    assert packet["source_set"] == {
        "source_classes": [
            "convention",
            "pin_contract",
            "receipt_diagnostic",
            "verifier_outcome",
        ],
        "source_paths": [
            PIN_SOURCE_PATH,
            DIAGNOSTIC_SOURCE_PATH,
            CONVENTION_SOURCE_PATH,
            VERIFY_SOURCE_PATH,
        ],
    }
    assert packet["unresolved_intent"] == []
    assert [item["criterion_id"] for item in packet["criteria"]] == [
        "output_a_assigned",
        "output_a_double_compatible",
        "verify_repair_succeeds",
        "preserve_body_mode",
        "resolve_target_diagnostics",
        "remove_unresolved_symbol",
    ]
    assert packet["criteria"] == [
        {
            "criterion_id": "output_a_assigned",
            "description": "Output A must be assigned.",
            "source": PIN_SOURCE_PATH,
            "source_class": "pin_contract",
        },
        {
            "criterion_id": "output_a_double_compatible",
            "description": "Output A must be double-compatible.",
            "source": PIN_SOURCE_PATH,
            "source_class": "pin_contract",
        },
        {
            "criterion_id": "verify_repair_succeeds",
            "description": (
                "The repaired body must satisfy the verify_repair "
                "expected_outcome: succeeded."
            ),
            "source": VERIFY_SOURCE_PATH,
            "source_class": "verifier_outcome",
        },
        {
            "criterion_id": "preserve_body_mode",
            "description": "The repair must preserve body-style code.",
            "source": CONVENTION_SOURCE_PATH,
            "source_class": "convention",
        },
        {
            "criterion_id": "resolve_target_diagnostics",
            "description": (
                "The repair must resolve the current target diagnostics."
            ),
            "source": DIAGNOSTIC_SOURCE_PATH,
            "source_class": "receipt_diagnostic",
        },
        {
            "criterion_id": "remove_unresolved_symbol",
            "description": (
                "The repaired body must not leave "
                "DefinitelyMissingSymbol unresolved."
            ),
            "source": DIAGNOSTIC_SOURCE_PATH,
            "source_class": "receipt_diagnostic",
        },
    ]
    assert packet["fingerprint"].startswith("sha256:")
```

- [ ] **Step 2: Run the test to verify it fails**

Run from repo root:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  -q
```

Expected: fails during import with:

```text
ModuleNotFoundError: No module named 'rook.agent.local_worker_acceptance_criteria'
```

- [ ] **Step 3: Implement the public module and canonical packet path**

Create `mcp_server/src/rook/agent/local_worker_acceptance_criteria.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any


ACCEPTANCE_CRITERIA_PACKET_SCHEMA = "rook.acceptance_criteria_packet:v1"

PIN_CONTRACT = "pin_contract"
VERIFIER_OUTCOME = "verifier_outcome"
RECEIPT_DIAGNOSTIC = "receipt_diagnostic"
CONVENTION = "convention"
PLANNER_USER_INTENT = "planner_user_intent"

_ALLOWED_SOURCE_CLASSES = {
    PIN_CONTRACT,
    VERIFIER_OUTCOME,
    RECEIPT_DIAGNOSTIC,
    CONVENTION,
    PLANNER_USER_INTENT,
}

_PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
_VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
_DIAGNOSTIC_SOURCE_PATH = (
    "create_script.receipt.script_receipt.repair_anchor.target_errors"
)
_CONVENTION_SOURCE_PATH = "script_body_gotcha"
_TARGET_SYMBOL = "DefinitelyMissingSymbol"

__all__ = (
    "ACCEPTANCE_CRITERIA_PACKET_SCHEMA",
    "AcceptanceCriteriaSource",
    "UnresolvedIntentEntry",
    "AcceptanceCriteriaSources",
    "assemble_acceptance_criteria_packet",
)


@dataclass(frozen=True)
class AcceptanceCriteriaSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class UnresolvedIntentEntry:
    intent_id: str
    description: str
    source_class: str
    source_path: str
    reason: str


@dataclass(frozen=True)
class AcceptanceCriteriaSources:
    pin_contract: AcceptanceCriteriaSource
    verifier_outcome: AcceptanceCriteriaSource
    receipt_diagnostic: AcceptanceCriteriaSource
    convention: AcceptanceCriteriaSource
    unresolved_intent: tuple[UnresolvedIntentEntry, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unresolved_intent",
            tuple(self.unresolved_intent),
        )


def assemble_acceptance_criteria_packet(
    sources: AcceptanceCriteriaSources,
) -> dict[str, Any]:
    pin_name, pin_type = _validate_pin_contract(sources.pin_contract)
    _validate_verifier_outcome(sources.verifier_outcome)
    _validate_receipt_diagnostic(sources.receipt_diagnostic)
    _validate_convention(sources.convention)
    unresolved_intent = _render_unresolved_intent(
        sources.unresolved_intent
    )

    criteria = [
        {
            "criterion_id": f"output_{pin_name.lower()}_assigned",
            "description": f"Output {pin_name} must be assigned.",
            "source": sources.pin_contract.source_path,
            "source_class": PIN_CONTRACT,
        },
        {
            "criterion_id": f"output_{pin_name.lower()}_double_compatible",
            "description": (
                f"Output {pin_name} must be {pin_type}-compatible."
            ),
            "source": sources.pin_contract.source_path,
            "source_class": PIN_CONTRACT,
        },
        {
            "criterion_id": "verify_repair_succeeds",
            "description": (
                "The repaired body must satisfy the verify_repair "
                "expected_outcome: succeeded."
            ),
            "source": sources.verifier_outcome.source_path,
            "source_class": VERIFIER_OUTCOME,
        },
        {
            "criterion_id": "preserve_body_mode",
            "description": "The repair must preserve body-style code.",
            "source": sources.convention.source_path,
            "source_class": CONVENTION,
        },
        {
            "criterion_id": "resolve_target_diagnostics",
            "description": (
                "The repair must resolve the current target diagnostics."
            ),
            "source": sources.receipt_diagnostic.source_path,
            "source_class": RECEIPT_DIAGNOSTIC,
        },
        {
            "criterion_id": "remove_unresolved_symbol",
            "description": (
                "The repaired body must not leave "
                "DefinitelyMissingSymbol unresolved."
            ),
            "source": sources.receipt_diagnostic.source_path,
            "source_class": RECEIPT_DIAGNOSTIC,
        },
    ]

    source_classes = sorted(
        {
            item["source_class"]
            for item in criteria
        }
        | {item["source_class"] for item in unresolved_intent}
    )
    source_paths = sorted(
        {item["source"] for item in criteria}
        | {item["source_path"] for item in unresolved_intent}
    )
    packet = {
        "schema": ACCEPTANCE_CRITERIA_PACKET_SCHEMA,
        "source_set": {
            "source_classes": source_classes,
            "source_paths": source_paths,
        },
        "criteria": criteria,
        "unresolved_intent": unresolved_intent,
    }
    packet["fingerprint"] = _fingerprint(packet)
    return packet


def _validate_source(
    source: AcceptanceCriteriaSource,
    *,
    expected_class: str,
) -> None:
    if source.source_class not in _ALLOWED_SOURCE_CLASSES:
        raise ValueError(f"unknown source class: {source.source_class!r}")
    if source.source_class != expected_class:
        raise ValueError(
            f"expected source class {expected_class!r}, "
            f"got {source.source_class!r}"
        )
    if not isinstance(source.source_path, str) or not source.source_path:
        raise ValueError("source_path must be a non-empty string")


def _validate_pin_contract(
    source: AcceptanceCriteriaSource,
) -> tuple[str, str]:
    _validate_source(source, expected_class=PIN_CONTRACT)
    if not isinstance(source.value, Mapping):
        raise ValueError("pin_contract value must be a mapping")
    pins_out = source.value.get("pins_out")
    if not isinstance(pins_out, list):
        raise ValueError("pin_contract pins_out must be a list")
    if len(pins_out) != 1:
        raise ValueError("LM5W v1 requires exactly one output pin")
    pin = pins_out[0]
    if not isinstance(pin, str) or pin.count(":") != 1:
        raise ValueError("output pin must be shaped as '<name>:<type>'")
    pin_name, pin_type = pin.split(":", 1)
    if not pin_name or not pin_type:
        raise ValueError("output pin name and type must be non-empty")
    if pin_name != "A" or pin_type != "double":
        raise ValueError("LM5W v1 requires pins_out == ['A:double']")
    return pin_name, pin_type


def _validate_verifier_outcome(source: AcceptanceCriteriaSource) -> None:
    _validate_source(source, expected_class=VERIFIER_OUTCOME)
    if source.value != "succeeded":
        raise ValueError("verifier_outcome value must be 'succeeded'")


def _validate_receipt_diagnostic(source: AcceptanceCriteriaSource) -> None:
    _validate_source(source, expected_class=RECEIPT_DIAGNOSTIC)
    diagnostics = source.value
    if not isinstance(diagnostics, list):
        raise ValueError("receipt_diagnostic value must be a list[str]")
    if not diagnostics:
        raise ValueError("receipt_diagnostic value must be non-empty")
    if any(not isinstance(item, str) for item in diagnostics):
        raise ValueError("receipt diagnostics must contain only strings")
    if not any(_TARGET_SYMBOL in item for item in diagnostics):
        raise ValueError("receipt diagnostics must mention DefinitelyMissingSymbol")


def _validate_convention(source: AcceptanceCriteriaSource) -> None:
    _validate_source(source, expected_class=CONVENTION)
    if not isinstance(source.value, Mapping):
        raise ValueError("convention value must be a mapping")
    if source.value.get("mode") != "body":
        raise ValueError("convention mode must be 'body'")


def _render_unresolved_intent(
    entries: tuple[UnresolvedIntentEntry, ...],
) -> list[dict[str, str]]:
    rendered: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, UnresolvedIntentEntry):
            raise ValueError(
                "unresolved_intent entries must be UnresolvedIntentEntry"
            )
        values = {
            "intent_id": entry.intent_id,
            "description": entry.description,
            "source_class": entry.source_class,
            "source_path": entry.source_path,
            "reason": entry.reason,
        }
        for field_name, value in values.items():
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"unresolved_intent {field_name} must be a non-empty string"
                )
        if entry.source_class != PLANNER_USER_INTENT:
            raise ValueError(
                "unresolved_intent entries must use planner_user_intent"
            )
        if entry.intent_id in seen_ids:
            raise ValueError("unresolved_intent intent_id values must be unique")
        seen_ids.add(entry.intent_id)
        rendered.append(values)
    return sorted(rendered, key=lambda item: item["intent_id"])


def _fingerprint(packet_without_fingerprint: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        packet_without_fingerprint,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
```

- [ ] **Step 4: Run the targeted test**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria.py
git commit -m "feat(lm5w): add acceptance criteria assembler"
```

---

### Task 2: Validation, Fingerprint, And Freshness Tests

**Files:**
- Modify: `mcp_server/tests/test_local_worker_acceptance_criteria.py`
- Modify: `mcp_server/src/rook/agent/local_worker_acceptance_criteria.py` only if Task 1 implementation missed a validation detail

- [ ] **Step 1: Add validation and fingerprint tests**

Append these tests to `mcp_server/tests/test_local_worker_acceptance_criteria.py`:

```python
def test_fingerprint_matches_canonical_json_without_fingerprint() -> None:
    packet = assemble_acceptance_criteria_packet(_valid_sources())
    expected = hashlib.sha256(
        json.dumps(
            _without_fingerprint(packet),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert packet["fingerprint"] == f"sha256:{expected}"


def test_fingerprint_is_stable_for_equivalent_source_dict_order() -> None:
    first = assemble_acceptance_criteria_packet(_valid_sources())
    second = assemble_acceptance_criteria_packet(
        _valid_sources(
            pin_contract=AcceptanceCriteriaSource(
                source_class="pin_contract",
                source_path=PIN_SOURCE_PATH,
                value={"pins_out": ["A:double"]},
            ),
            convention=AcceptanceCriteriaSource(
                source_class="convention",
                source_path=CONVENTION_SOURCE_PATH,
                value=dict([("mode", "body")]),
            ),
        )
    )
    assert second["fingerprint"] == first["fingerprint"]


def test_fingerprint_changes_when_source_path_changes() -> None:
    first = assemble_acceptance_criteria_packet(_valid_sources())
    second = assemble_acceptance_criteria_packet(
        _valid_sources(
            convention=AcceptanceCriteriaSource(
                source_class="convention",
                source_path="script_body_gotcha.v2",
                value={"mode": "body"},
            )
        )
    )
    assert second["fingerprint"] != first["fingerprint"]


def test_returned_packet_is_fresh_across_calls() -> None:
    first = assemble_acceptance_criteria_packet(_valid_sources())
    first["criteria"][0]["description"] = "bad"
    first["source_set"]["source_classes"].append("bad")
    first["unresolved_intent"].append({"intent_id": "bad"})

    second = assemble_acceptance_criteria_packet(_valid_sources())
    assert second["criteria"][0]["description"] == "Output A must be assigned."
    assert "bad" not in second["source_set"]["source_classes"]
    assert second["unresolved_intent"] == []


def test_unresolved_intent_entries_are_sorted_and_indexed() -> None:
    baseline = assemble_acceptance_criteria_packet(_valid_sources())
    packet = assemble_acceptance_criteria_packet(
        _valid_sources(
            unresolved_intent=[
                UnresolvedIntentEntry(
                    intent_id="z_missing_design_goal",
                    description="A design goal was not provided.",
                    source_class="planner_user_intent",
                    source_path="planner.intent.design_goal",
                    reason="missing",
                ),
                UnresolvedIntentEntry(
                    intent_id="a_missing_output_value",
                    description="A desired output value was not provided.",
                    source_class="planner_user_intent",
                    source_path="planner.intent.desired_output_value",
                    reason="missing",
                ),
            ]
        )
    )

    assert [item["intent_id"] for item in packet["unresolved_intent"]] == [
        "a_missing_output_value",
        "z_missing_design_goal",
    ]
    assert "planner_user_intent" in packet["source_set"]["source_classes"]
    assert "planner.intent.design_goal" in packet["source_set"]["source_paths"]
    assert packet["fingerprint"] != baseline["fingerprint"]


@pytest.mark.parametrize(
    ("override", "match"),
    [
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="wrong",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["A:double"]},
                )
            },
            "unknown source class|expected source class",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path="",
                    value={"pins_out": ["A:double"]},
                )
            },
            "source_path",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": []},
                )
            },
            "exactly one output pin",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["A:double", "B:int"]},
                )
            },
            "exactly one output pin",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["A"]},
                )
            },
            "<name>:<type>",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["B:int"]},
                )
            },
            "A:double",
        ),
        (
            {
                "verifier_outcome": AcceptanceCriteriaSource(
                    source_class="verifier_outcome",
                    source_path=VERIFY_SOURCE_PATH,
                    value="needs_repair",
                )
            },
            "succeeded",
        ),
        (
            {
                "convention": AcceptanceCriteriaSource(
                    source_class="convention",
                    source_path=CONVENTION_SOURCE_PATH,
                    value={"mode": "script"},
                )
            },
            "body",
        ),
        (
            {
                "receipt_diagnostic": AcceptanceCriteriaSource(
                    source_class="receipt_diagnostic",
                    source_path=DIAGNOSTIC_SOURCE_PATH,
                    value=[],
                )
            },
            "non-empty",
        ),
        (
            {
                "receipt_diagnostic": AcceptanceCriteriaSource(
                    source_class="receipt_diagnostic",
                    source_path=DIAGNOSTIC_SOURCE_PATH,
                    value=["CS0000: Different diagnostic"],
                )
            },
            "DefinitelyMissingSymbol",
        ),
        (
            {
                "receipt_diagnostic": AcceptanceCriteriaSource(
                    source_class="receipt_diagnostic",
                    source_path=DIAGNOSTIC_SOURCE_PATH,
                    value=[123],
                )
            },
            "strings",
        ),
    ],
)
def test_validation_fails_closed(override, match) -> None:
    with pytest.raises(ValueError, match=match):
        assemble_acceptance_criteria_packet(_valid_sources(**override))


def test_unresolved_intent_wrong_source_class_fails() -> None:
    with pytest.raises(ValueError, match="planner_user_intent"):
        assemble_acceptance_criteria_packet(
            _valid_sources(
                unresolved_intent=[
                    UnresolvedIntentEntry(
                        intent_id="desired_output_value",
                        description="No desired output value was provided.",
                        source_class="pin_contract",
                        source_path="planner.intent.desired_output_value",
                        reason="missing",
                    )
                ]
            )
        )


def test_unresolved_intent_empty_field_fails() -> None:
    with pytest.raises(ValueError, match="intent_id"):
        assemble_acceptance_criteria_packet(
            _valid_sources(
                unresolved_intent=[
                    UnresolvedIntentEntry(
                        intent_id="",
                        description="No desired output value was provided.",
                        source_class="planner_user_intent",
                        source_path="planner.intent.desired_output_value",
                        reason="missing",
                    )
                ]
            )
        )


def test_unresolved_intent_wrong_entry_type_fails() -> None:
    with pytest.raises(ValueError, match="UnresolvedIntentEntry"):
        assemble_acceptance_criteria_packet(
            _valid_sources(
                unresolved_intent=[
                    {
                        "intent_id": "desired_output_value",
                        "description": "No desired output value was provided.",
                        "source_class": "planner_user_intent",
                        "source_path": "planner.intent.desired_output_value",
                        "reason": "missing",
                    }
                ]
            )
        )
```

- [ ] **Step 2: Run the targeted test**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  -q
```

Expected: all tests in the file pass. If any validation test fails because Task 1 did not implement the corresponding fail-closed rule, patch `local_worker_acceptance_criteria.py` only to add that exact rule.

- [ ] **Step 3: Commit Task 2**

Run:

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria.py
git commit -m "test(lm5w): cover acceptance criteria validation"
```

---

### Task 3: Fixture Reproduction Anchor And Static Guards

**Files:**
- Modify: `mcp_server/tests/test_local_worker_acceptance_criteria.py`
- Do not modify probe scripts

- [ ] **Step 1: Add fixture reproduction and import-boundary helpers**

Append these helpers and tests to `mcp_server/tests/test_local_worker_acceptance_criteria.py`:

```python
def _load_lm5k_probe_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe_for_lm5w", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _jsonable(value):
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def test_fixture_reproduction_anchor_matches_lm5u_legacy_projection() -> None:
    probe = _load_lm5k_probe_script()
    _scaffold, result = probe.derive_probe_graph_state()
    lm5u_packet = _jsonable(
        probe._acceptance_criteria_evidence_packet(result.final_graph).content
    )
    lm5u_packet_acceptance_criteria = (
        lm5u_packet["fields"]["acceptance_criteria"]["criteria"]
    )

    sources = AcceptanceCriteriaSources(
        pin_contract=AcceptanceCriteriaSource(
            source_class="pin_contract",
            source_path=PIN_SOURCE_PATH,
            value={"pins_out": ["A:double"]},
        ),
        verifier_outcome=AcceptanceCriteriaSource(
            source_class="verifier_outcome",
            source_path=VERIFY_SOURCE_PATH,
            value="succeeded",
        ),
        receipt_diagnostic=AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[probe.REPAIR_TARGET_ERROR],
        ),
        convention=AcceptanceCriteriaSource(
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
            value={"mode": "body"},
        ),
    )
    assembled = assemble_acceptance_criteria_packet(sources)
    legacy_projection = [
        {
            "criterion_id": criterion["criterion_id"],
            "description": criterion["description"],
            "source": criterion["source"],
        }
        for criterion in assembled["criteria"]
    ]

    assert legacy_projection == lm5u_packet_acceptance_criteria
    assert [criterion["source_class"] for criterion in assembled["criteria"]] == [
        "pin_contract",
        "pin_contract",
        "verifier_outcome",
        "convention",
        "receipt_diagnostic",
        "receipt_diagnostic",
    ]


def test_module_import_boundary_stays_narrow() -> None:
    import rook.agent.local_worker_acceptance_criteria as module

    source = inspect.getsource(module)
    forbidden = (
        "plan_graph",
        "RookWorkflowContract",
        "CompiledWorkflowScaffold",
        "lm5k_worker_probe",
        "lm5r_two_pass_publication_probe",
        "LiteLLM",
        "run_local_worker",
        "open(",
        "Path(",
        "json.load",
        "yaml",
    )
    for token in forbidden:
        assert token not in source
```

- [ ] **Step 2: Run the targeted test**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  -q
```

Expected: all tests in the file pass.

- [ ] **Step 3: Confirm probe scripts did not import the new module**

Run:

```powershell
rg "local_worker_acceptance_criteria" scripts\lm5k_worker_probe.py scripts\lm5r_two_pass_publication_probe.py
```

Expected: no output.

- [ ] **Step 4: Commit Task 3**

Run:

```powershell
git add mcp_server\tests\test_local_worker_acceptance_criteria.py
git commit -m "test(lm5w): anchor assembler to LM5U fixture"
```

---

### Task 4: Final Verification Gates

**Files:**
- No source edits unless a gate exposes an LM5W issue

- [ ] **Step 1: Run targeted LM5W tests**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  -q
```

Expected: all LM5W tests pass.

- [ ] **Step 2: Run nearby probe/worker tests**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all selected tests pass. Do not run the full pytest suite.

- [ ] **Step 3: Run Python 3.10 compile gate**

Run from repo root:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria.py
```

Expected: no output.

- [ ] **Step 4: Confirm exact tracked scope**

Run:

```powershell
git diff --name-only main..HEAD
```

Compare the output as a set. Expected paths:

```text
docs/superpowers/specs/2026-07-05-lm5w-acceptance-criteria-assembly-boundary-design.md
docs/superpowers/plans/2026-07-05-lm5w-acceptance-criteria-assembly-boundary.md
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
mcp_server/tests/test_local_worker_acceptance_criteria.py
```

- [ ] **Step 5: Confirm no package export, probe, or production drift**

Run:

```powershell
git diff --name-only main..HEAD |
  rg "mcp_server/src/rook/agent/__init__\.py|scripts/lm5k_worker_probe\.py|scripts/lm5r_two_pass_publication_probe\.py|mcp_server/src/rook/agent/plan_graph_workflow_contract\.py"
```

Expected: no output.

Run:

```powershell
rg "local_worker_acceptance_criteria" scripts\lm5k_worker_probe.py scripts\lm5r_two_pass_publication_probe.py
```

Expected: no output.

- [ ] **Step 6: Run whitespace/static diff check**

Run:

```powershell
git diff --check main..HEAD
```

Expected: no output.

- [ ] **Step 7: Confirm working tree cleanliness**

Run:

```powershell
git status --short --branch
```

Expected:

- branch is the LM5W work branch
- tracked files clean after commits
- only pre-existing unrelated untracked files may remain, such as `.understand-anything/` and Rook2 docs

- [ ] **Step 8: Do not run live/model/probe artifacts**

Confirm no LM5W step created:

```text
probe_runs/
model calls
Ollama calls
Anthropic calls
curated evidence summary edits
```

LM5W is deterministic only.
