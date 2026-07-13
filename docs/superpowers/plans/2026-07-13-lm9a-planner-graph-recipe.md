# LM9A Planner Graph Recipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an offline, model-free `rook.planner_graph_recipe:v1` validator with an explicit invocation preflight, deterministic `rook.planner_graph_recipe_validation_report:v1` artifacts after successful preflight, and generic radial, non-radial, worker-slot, and confirmation proofs.

**Architecture:** Add a new LM9A-only validation stack beside the existing Planner/worker and workflow-contract code. A mechanical invocation preflight first establishes validator identity and exact recipe bytes, copies caller-owned validation input into one immutable JSON/JCS-domain snapshot, and proves that every mandatory report descriptor shell exists. After it succeeds, raw recipe bytes and independent thawed snapshot views enter closed validation phases, exact RFC 8785 canonicalization establishes identity, and one orchestrator emits the closed report. Recipe schema and companion phases are independent, so one report may receipt both failures. Preflight, validator-integrity, or implementation failure before complete report publication returns a typed non-artifact control result rather than a partial report. The implementation must not compile, schedule, execute, call tools, or mutate the existing Planner/worker protocols.

**Tech Stack:** Python 3.10+, stdlib `json`/`hashlib`/`decimal`/`unicodedata`, `jsonschema` Draft 2020-12 validation with its `referencing` registry and `jsonschema-specifications` metaschema dependencies (the already-locked `4.26.0`, `0.37.0`, and `2025.9.1` packages promoted to direct dependencies), `pytest`.

## Global Constraints

- Implement exactly the LM9A scope in `docs/superpowers/specs/2026-07-13-lm9a-planner-graph-recipe-design.md`.
- Keep `PlannerWorkerContractRequest:v1`, `RookWorkflowContract`, `TaskSpec`, `workflow_validate`, and their public behavior unchanged.
- No Planner model, worker model, provider routing, prompt rendering, tool call, `gh_edit`, Rhino/Grasshopper process, compiler, semantic-review gateway, executor, or live run.
- The validator returns either one validation report after successful preflight or one typed `ValidationInvocationFailure` control result. The failure is not a Rook artifact or partial report. The validator never emits compiler requests, worker requests, compiled IR, executable artifacts, or runtime receipts.
- Python support remains `>=3.10`.
- `jsonschema==4.26.0`, `referencing==0.37.0`, and `jsonschema-specifications==2025.9.1` are already present in `mcp_server/uv.lock`; promote those exact resolved packages to direct dependencies without adding another package or changing any resolved version.
- `rook.canonical_json:v1` is a new exact RFC 8785 regime. Do not import, call, wrap, copy, or imitate `_fingerprint_normalized_contract` or any other legacy canonical JSON helper.
- Recipe input is exact raw UTF-8 bytes without BOM, capped inclusively at 1,048,576 bytes, 64 array/object container levels, and 1,024 characters per JSON number token. Duplicate object members, unpaired surrogates, invalid UTF-8, decoder recursion, oversized numeric tokens, non-finite numeric conversion, and nonconforming product numbers fail closed into a schema-phase report after preflight succeeds.
- Validation input is copied once during preflight into an immutable tagged JSON snapshot. The snapshot rejects depth over 64, repeated/cyclic containers, non-string keys, unpaired surrogates, non-finite floats, integers outside the finite JCS domain, and non-JSON host values. Later phases never retain or read caller-owned containers.
- Exact JCS serialization accepts the complete finite RFC 8785 number domain. Product-number policy, including the interoperable integer range, is enforced only by schema/product validation; embedded JSON Schema documents are exempt from that product-number policy.
- Hashes are lowercase `sha256:<hex>` strings.
- All production LM9A modules are domain-neutral. Radial, box-array, grid-spacing, height-falloff, and layer-control scenario terms belong only in test fixture modules and documentation.
- Preserve unrelated local knowledge, draft, and telemetry changes. Stage only files named by the current task.
- Every task uses TDD and ends with its own focused verification and commit.

---

## File Map

Production modules:

- `mcp_server/src/rook/agent/planner_graph_recipe_canonical.py`: strict raw JSON ingress, exact RFC 8785 serialization, UTF-16 comparison, and fingerprint primitives.
- `mcp_server/src/rook/agent/planner_graph_recipe_schemas.py`: closed Draft 2020-12 schemas, schema-directed normalization, exhaustive set ordering, product-number rules, and local-only registered payload-schema validation.
- `mcp_server/src/rook/agent/planner_graph_recipe_report.py`: diagnostic/blocker records, phase derivation, deterministic issue ordering, descriptor shapes, and report assembly helpers.
- `mcp_server/src/rook/agent/planner_graph_recipe_authority.py`: companion indexing, trusted fingerprint/session/freshness checks, RFC 6901 resolution, value bindings, vocabularies, capability registry, and policy registry validation.
- `mcp_server/src/rook/agent/planner_graph_recipe_semantics.py`: clause graph, source coverage, derived facts, assumptions, confirmations, unresolved intent, shape, capabilities, worker slots, and readiness validation.
- `mcp_server/src/rook/agent/planner_graph_recipe_rules.py`: versioned rule manifest, stable phase/code registry, normalized production-module source projection, and ruleset fingerprint.
- `mcp_server/src/rook/agent/planner_graph_recipe_validate.py`: public raw-bytes validation entry point and fixed phase orchestration.

Test support and tests:

- `mcp_server/tests/lm9a_contract_factory.py`: generic, domain-neutral companion and recipe builders used by focused unit tests.
- `mcp_server/tests/lm9a_fixture_factory.py`: radial pair, non-radial layer control, worker-slot, confirmation, and pair-manifest fixtures.
- `mcp_server/tests/fixtures/lm9a/rfc8785_number_vectors.json`: exact RFC 8785 Appendix B double-serialization vectors.
- `mcp_server/tests/test_planner_graph_recipe_canonical.py`
- `mcp_server/tests/test_planner_graph_recipe_schemas.py`
- `mcp_server/tests/test_planner_graph_recipe_report.py`
- `mcp_server/tests/test_planner_graph_recipe_authority.py`
- `mcp_server/tests/test_planner_graph_recipe_semantics.py`
- `mcp_server/tests/test_planner_graph_recipe_rules.py`
- `mcp_server/tests/test_planner_graph_recipe_validate.py`
- `mcp_server/tests/test_lm9a_planner_graph_recipe_fixtures.py`
- `mcp_server/tests/test_lm9a_planner_graph_recipe_boundaries.py`

Existing dependency metadata:

- `mcp_server/pyproject.toml`
- `mcp_server/uv.lock`

## Spec Coverage Map

| Spec area | Implemented/proved by |
|---|---|
| Artifact boundary and closed validation input (Sections 4.1-4.7) | Tasks 2 and 4 |
| Validation invocation preflight (Section 8.0) | Task 8 |
| Materiality, honest validation limits, IDs, references, and clause support (Section 5) | Tasks 2, 4, and 5 |
| Full recipe grammar (Sections 6.1-6.11) | Tasks 2 and 5-7 |
| Authority/conflict matrix (Section 7) | Tasks 4 and 6 |
| Validation report, descriptors, statuses, and phase graph (Section 8) | Tasks 3 and 8 |
| Exact canonicalization/fingerprints (Section 9) | Tasks 1, 2, and 8 |
| Future compile/review constraints remain unimplemented (Section 10) | Global constraints and Task 10 guards |
| Radial pair, control, slot, and confirmation fixtures (Section 11) | Task 9 |
| Positive, negative, and anti-overfitting proofs (Section 12) | Tasks 1-10, with the cross-cutting matrix in Task 10 |
| Existing artifact boundaries remain unchanged (Section 13) | Task 10 AST/import and nearby regression gates |

---

### Task 1: Exact RFC 8785 Canonical Bytes And Raw Ingress

**Files:**
- Create: `mcp_server/src/rook/agent/planner_graph_recipe_canonical.py`
- Create: `mcp_server/tests/fixtures/lm9a/rfc8785_number_vectors.json`
- Create: `mcp_server/tests/test_planner_graph_recipe_canonical.py`

**Interfaces:**
- Consumes: raw `bytes` and already schema-valid JSON values.
- Produces:
  - `RawJsonResult(payload: Any | None, input_payload_sha256: str, error_code: str | None, error_message: str | None)`
  - `parse_raw_json(raw: bytes) -> RawJsonResult`
  - `validate_json_tree(value: Any, *, depth_error_code: str = "json_container_depth_exceeded", nonfinite_error_code: str = "nonfinite_json_number") -> None`
  - `JsonSnapshotError(code: str, path: str, message: str)`
  - `FrozenJsonObject(items: tuple[tuple[str, FrozenJsonValue], ...])`
  - `FrozenJsonArray(items: tuple[FrozenJsonValue, ...])`
  - `JsonSnapshot(value: FrozenJsonValue, fingerprint: str)` with `thaw() -> Any`
  - `snapshot_json_tree(value: Mapping[str, Any], *, max_depth: int = 64) -> JsonSnapshot`
  - `utf16_sort_key(value: str) -> bytes`
  - `canonical_json_bytes(value: Any) -> bytes`
  - `canonical_sha256(value: Any) -> str`
  - `typed_value_fingerprint(typed_value: Mapping[str, Any]) -> str`
  - `normalize_semantic_prose(value: str) -> str`
  - `normalize_lf(value: str) -> str`
  - `compare_compound(left: tuple[Any, ...], right: tuple[Any, ...]) -> int`
  - `bounded_message(base: str, detail: str | None = None) -> str`
  - `MAX_EVIDENCE_MESSAGE_CHARS = 512`
  - `MAX_RECIPE_INPUT_BYTES = 1_048_576`
  - `MAX_JSON_CONTAINER_DEPTH = 64`
  - `MAX_JSON_NUMBER_TOKEN_CHARS = 1_024`

- [ ] **Step 1: Write strict-ingress and Unicode-ordering tests**

```python
from __future__ import annotations

import json
import pathlib
import struct
from collections import UserDict
from decimal import Decimal

import pytest

from rook.agent.planner_graph_recipe_canonical import (
    CanonicalJsonError,
    JsonSnapshotError,
    MAX_JSON_CONTAINER_DEPTH,
    MAX_JSON_NUMBER_TOKEN_CHARS,
    MAX_RECIPE_INPUT_BYTES,
    canonical_json_bytes,
    canonical_sha256,
    compare_compound,
    parse_raw_json,
    snapshot_json_tree,
    utf16_sort_key,
)


def test_raw_ingress_hashes_exact_bytes_before_rejecting_bom():
    raw = b"\xef\xbb\xbf{}"
    parsed = parse_raw_json(raw)
    assert parsed.payload is None
    assert parsed.input_payload_sha256.startswith("sha256:")
    assert parsed.error_code == "utf8_bom_forbidden"


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"x":1,"x":2}', "duplicate_object_member"),
        (b'{"x":"\\ud800"}', "unpaired_unicode_surrogate"),
        (b"\xff", "invalid_utf8"),
    ],
)
def test_raw_ingress_rejects_noncanonical_json_inputs(raw, code):
    assert parse_raw_json(raw).error_code == code


def test_raw_ingress_enforces_exact_byte_limit_before_decoding():
    at_limit = b"0" + (b" " * (MAX_RECIPE_INPUT_BYTES - 1))
    accepted = parse_raw_json(at_limit)
    assert accepted.payload == 0
    assert accepted.error_code is None

    over_limit = at_limit + b" "
    rejected = parse_raw_json(over_limit)
    assert rejected.payload is None
    assert rejected.error_code == "recipe_input_bytes_exceeded"
    assert rejected.input_payload_sha256.startswith("sha256:")


def test_raw_ingress_enforces_container_depth_iteratively():
    at_limit = (
        (b"[" * MAX_JSON_CONTAINER_DEPTH)
        + b"0"
        + (b"]" * MAX_JSON_CONTAINER_DEPTH)
    )
    assert parse_raw_json(at_limit).error_code is None

    over_limit = b"[" + at_limit + b"]"
    assert parse_raw_json(over_limit).error_code == "recipe_json_depth_exceeded"


def test_decoder_recursion_is_receipted_as_depth_failure():
    deeper_than_python_decoder = (b"[" * 2_000) + b"0" + (b"]" * 2_000)
    parsed = parse_raw_json(deeper_than_python_decoder)
    assert parsed.payload is None
    assert parsed.error_code == "recipe_json_depth_exceeded"


def test_float_overflow_token_is_rejected_before_nonfinite_value_enters_tree():
    parsed = parse_raw_json(b'{"value":1e10000}')
    assert parsed.payload is None
    assert parsed.error_code == "nonfinite_json_number"


def test_integer_token_is_bounded_before_host_integer_conversion():
    token = b"9" * 5_000
    parsed = parse_raw_json(b'{"value":' + token + b"}")
    assert parsed.payload is None
    assert parsed.error_code == "json_number_token_too_long"


def test_number_token_limit_is_inclusive():
    token = b"1." + (b"0" * (MAX_JSON_NUMBER_TOKEN_CHARS - 2))
    assert len(token) == MAX_JSON_NUMBER_TOKEN_CHARS
    parsed = parse_raw_json(b'{"value":' + token + b"}")
    assert parsed.error_code is None
    assert parsed.payload["value"] == 1.0


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda root: root.update(value=float("inf")), "validation_input_snapshot_nonfinite_number"),
        (lambda root: root.update(value=10**400), "validation_input_snapshot_integer_out_of_jcs_domain"),
        (lambda root: root.update(value=Decimal("1")), "validation_input_snapshot_non_json_host_type"),
        (lambda root: root.update(value=b"x"), "validation_input_snapshot_non_json_host_type"),
        (lambda root: root.update(value=(1, 2)), "validation_input_snapshot_non_json_host_type"),
    ],
)
def test_validation_input_snapshot_rejects_values_outside_json_jcs_domain(
    mutate,
    code,
):
    candidate = {"value": 1}
    mutate(candidate)
    with pytest.raises(JsonSnapshotError, match=code):
        snapshot_json_tree(candidate)


def test_validation_input_snapshot_is_detached_from_original_mapping():
    original = UserDict({"nested": {"value": 1}})
    snapshot = snapshot_json_tree(original)
    original["nested"]["value"] = 99
    assert snapshot.thaw() == {"nested": {"value": 1}}
    assert snapshot.fingerprint == canonical_sha256({"nested": {"value": 1}})


def test_validation_input_snapshot_rejects_mapping_that_changes_between_passes():
    class FlippingMapping(UserDict):
        calls = 0

        def items(self):
            self.calls += 1
            return (("value", self.calls),)

    with pytest.raises(JsonSnapshotError, match="unstable_mapping"):
        snapshot_json_tree(FlippingMapping())


def test_validation_input_snapshot_rejects_repeated_or_cyclic_containers():
    shared = []
    with pytest.raises(JsonSnapshotError, match="repeated_container"):
        snapshot_json_tree({"left": shared, "right": shared})
    cycle = []
    cycle.append(cycle)
    with pytest.raises(JsonSnapshotError, match="repeated_container"):
        snapshot_json_tree({"cycle": cycle})


def test_validation_input_snapshot_depth_limit_is_inclusive():
    value = 0
    for _ in range(63):
        value = [value]
    assert snapshot_json_tree({"value": value}).fingerprint.startswith("sha256:")

    with pytest.raises(JsonSnapshotError, match="snapshot_depth_exceeded"):
        snapshot_json_tree({"value": [value]})


def test_object_keys_use_utf16_code_unit_order():
    payload = {"\U00010000": 1, "\ue000": 2}
    assert canonical_json_bytes(payload) == (
        '{"\U00010000":1,"\ue000":2}'.encode("utf-8")
    )
    assert utf16_sort_key("\U00010000") < utf16_sort_key("\ue000")


def test_strings_preserve_non_ascii_and_escape_json_controls_exactly():
    value = {"x": "Euro: €\nquote=\" slash=/ backslash=\\"}
    assert canonical_json_bytes(value) == (
        '{"x":"Euro: €\\nquote=\\" slash=/ backslash=\\\\"}'.encode("utf-8")
    )


def test_compound_lists_compare_lexicographically_shorter_prefix_first():
    assert compare_compound(("x", ["/a"]), ("x", ["/a", "/b"])) < 0
    assert compare_compound(("x", ["/b"]), ("x", ["/a", "/z"])) > 0


def test_oversized_duplicate_member_does_not_enter_error_message():
    hostile = "x" * 100_000
    raw = ('{"' + hostile + '":1,"' + hostile + '":2}').encode("utf-8")
    parsed = parse_raw_json(raw)
    assert parsed.error_code == "duplicate_object_member"
    assert len(parsed.error_message or "") <= 512
    assert hostile not in (parsed.error_message or "")
    assert "detail_sha256=sha256:" in (parsed.error_message or "")
```

- [ ] **Step 2: Add the exact RFC number vector fixture and tests**

Create `mcp_server/tests/fixtures/lm9a/rfc8785_number_vectors.json` with these exact Appendix B rows:

```json
[
  ["0000000000000000", "0"],
  ["8000000000000000", "0"],
  ["0000000000000001", "5e-324"],
  ["8000000000000001", "-5e-324"],
  ["7fefffffffffffff", "1.7976931348623157e+308"],
  ["ffefffffffffffff", "-1.7976931348623157e+308"],
  ["4340000000000000", "9007199254740992"],
  ["c340000000000000", "-9007199254740992"],
  ["4430000000000000", "295147905179352830000"],
  ["44b52d02c7e14af5", "9.999999999999997e+22"],
  ["44b52d02c7e14af6", "1e+23"],
  ["44b52d02c7e14af7", "1.0000000000000001e+23"],
  ["444b1ae4d6e2ef4e", "999999999999999700000"],
  ["444b1ae4d6e2ef4f", "999999999999999900000"],
  ["444b1ae4d6e2ef50", "1e+21"],
  ["3eb0c6f7a0b5ed8c", "9.999999999999997e-7"],
  ["3eb0c6f7a0b5ed8d", "0.000001"],
  ["41b3de4355555553", "333333333.3333332"],
  ["41b3de4355555554", "333333333.33333325"],
  ["41b3de4355555555", "333333333.3333333"],
  ["41b3de4355555556", "333333333.3333334"],
  ["41b3de4355555557", "333333333.33333343"],
  ["becbf647612f3696", "-0.0000033333333333333333"],
  ["43143ff3c1cb0959", "1424953923781206.2"]
]
```

Add this test:

```python
def test_rfc8785_appendix_b_number_vectors():
    fixture = pathlib.Path(__file__).parent / "fixtures/lm9a/rfc8785_number_vectors.json"
    for ieee_hex, expected in json.loads(fixture.read_text(encoding="utf-8")):
        value = struct.unpack(">d", bytes.fromhex(ieee_hex))[0]
        assert canonical_json_bytes(value).decode("utf-8") == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_numbers_are_rejected(value):
    with pytest.raises(CanonicalJsonError, match="nonfinite_json_number"):
        canonical_json_bytes(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (9007199254740992, "9007199254740992"),
        (9007199254740993, "9007199254740992"),
        (10**23, "1e+23"),
    ],
)
def test_integer_form_numbers_use_the_same_ieee754_jcs_domain(value, expected):
    assert canonical_json_bytes(value).decode("utf-8") == expected
```

- [ ] **Step 3: Run the focused tests to establish the red state**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_canonical.py -q
```

Expected: collection fails because `planner_graph_recipe_canonical` does not exist.

- [ ] **Step 4: Implement the isolated JCS adapter and raw parser**

Use these exact public types and keep the serializer self-contained:

```python
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from functools import cmp_to_key
from typing import Any, Mapping


SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_EVIDENCE_MESSAGE_CHARS = 512
MAX_RECIPE_INPUT_BYTES = 1_048_576
MAX_JSON_CONTAINER_DEPTH = 64
MAX_JSON_NUMBER_TOKEN_CHARS = 1_024


class CanonicalJsonError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RawJsonResult:
    payload: Any | None
    input_payload_sha256: str
    error_code: str | None
    error_message: str | None


def sha256_prefixed(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def bounded_message(base: str, detail: str | None = None) -> str:
    if detail is None:
        return base[:MAX_EVIDENCE_MESSAGE_CHARS]
    detail_hash = sha256_prefixed(detail.encode("utf-8", errors="surrogatepass"))
    suffix = f" detail_sha256={detail_hash}"
    return base[: MAX_EVIDENCE_MESSAGE_CHARS - len(suffix)] + suffix


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJsonError(
                "duplicate_object_member",
                bounded_message("Duplicate JSON object member rejected.", key),
            )
        result[key] = value
    return result


def _reject_surrogate_string(value: str) -> None:
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise CanonicalJsonError(
            "unpaired_unicode_surrogate",
            "JSON strings may not contain surrogate code points.",
        )


def validate_json_tree(
    value: Any,
    *,
    depth_error_code: str = "json_container_depth_exceeded",
    nonfinite_error_code: str = "nonfinite_json_number",
) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, parent_container_depth = stack.pop()
        if isinstance(node, str):
            _reject_surrogate_string(node)
            continue
        if isinstance(node, float) and not math.isfinite(node):
            raise CanonicalJsonError(
                nonfinite_error_code,
                "JSON trees may contain only finite numbers.",
            )
        if isinstance(node, list):
            container_depth = parent_container_depth + 1
            if container_depth > MAX_JSON_CONTAINER_DEPTH:
                raise CanonicalJsonError(
                    depth_error_code,
                    "JSON container depth exceeds 64.",
                )
            stack.extend((item, container_depth) for item in reversed(node))
            continue
        if isinstance(node, dict):
            container_depth = parent_container_depth + 1
            if container_depth > MAX_JSON_CONTAINER_DEPTH:
                raise CanonicalJsonError(
                    depth_error_code,
                    "JSON container depth exceeds 64.",
                )
            for key, item in reversed(tuple(node.items())):
                if not isinstance(key, str):
                    raise CanonicalJsonError(
                        "invalid_json_object_key",
                        "JSON object keys must be strings.",
                    )
                _reject_surrogate_string(key)
                stack.append((item, container_depth))


def _check_number_token(token: str) -> None:
    if len(token) > MAX_JSON_NUMBER_TOKEN_CHARS:
        raise CanonicalJsonError(
            "json_number_token_too_long",
            "JSON number token exceeds 1024 characters.",
        )


def _parse_json_int(token: str) -> int:
    _check_number_token(token)
    try:
        sign = -1 if token.startswith("-") else 1
        digits = token[1:] if sign < 0 else token
        value = 0
        for offset in range(0, len(digits), 18):
            chunk = digits[offset : offset + 18]
            value = (value * (10 ** len(chunk))) + int(chunk)
        return sign * value
    except (ValueError, OverflowError) as exc:
        raise CanonicalJsonError(
            "invalid_json_number",
            "JSON integer conversion failed.",
        ) from exc


def _parse_json_float(token: str) -> float:
    _check_number_token(token)
    try:
        value = float(token)
    except (ValueError, OverflowError) as exc:
        raise CanonicalJsonError(
            "invalid_json_number",
            "JSON number conversion failed.",
        ) from exc
    if not math.isfinite(value):
        raise CanonicalJsonError(
            "nonfinite_json_number",
            "JSON number is outside the finite IEEE 754 domain.",
        )
    return value


def _reject_json_constant(_token: str) -> None:
    raise CanonicalJsonError(
        "nonfinite_json_number",
        "Non-finite JSON constants are forbidden.",
    )


def parse_raw_json(raw: bytes) -> RawJsonResult:
    digest = sha256_prefixed(raw)
    if len(raw) > MAX_RECIPE_INPUT_BYTES:
        return RawJsonResult(
            None,
            digest,
            "recipe_input_bytes_exceeded",
            "Recipe input exceeds 1048576 bytes.",
        )
    if raw.startswith(b"\xef\xbb\xbf"):
        return RawJsonResult(None, digest, "utf8_bom_forbidden", "UTF-8 BOM is forbidden.")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return RawJsonResult(
            None,
            digest,
            "invalid_utf8",
            "Recipe bytes are not valid UTF-8.",
        )
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_int=_parse_json_int,
            parse_float=_parse_json_float,
            parse_constant=_reject_json_constant,
        )
        validate_json_tree(payload, depth_error_code="recipe_json_depth_exceeded")
    except RecursionError:
        return RawJsonResult(
            None,
            digest,
            "recipe_json_depth_exceeded",
            "Recipe JSON exceeds the supported container depth.",
        )
    except (json.JSONDecodeError, CanonicalJsonError) as exc:
        code = exc.code if isinstance(exc, CanonicalJsonError) else "invalid_json"
        message = exc.message if isinstance(exc, CanonicalJsonError) else bounded_message(
            "Recipe JSON is malformed.", str(exc)
        )
        return RawJsonResult(None, digest, code, message)
    except ValueError:
        # Defensive host-runtime fence for decoder conversion failures not
        # normalized by the bounded callbacks above.
        return RawJsonResult(
            None,
            digest,
            "invalid_json_number",
            "JSON numeric conversion failed.",
        )
    return RawJsonResult(payload, digest, None, None)


def utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be", errors="strict")


def normalize_lf(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def normalize_semantic_prose(value: str) -> str:
    normalized = unicodedata.normalize("NFC", normalize_lf(value))
    if normalized != normalized.strip():
        raise CanonicalJsonError(
            "semantic_prose_outer_whitespace",
            "Semantic prose may not have leading or trailing whitespace.",
        )
    return normalized
```

Depth is the number of containing array/object nodes along a value path: a
top-level scalar has depth `0`, a top-level array/object has depth `1`, and the
64th nested container is accepted while the 65th is rejected. The byte limit
applies to the exact received recipe bytes before BOM detection or decoding,
but the exact-byte SHA-256 is still recorded for an over-limit input.
The number-token limit counts the complete token supplied by `json.loads`,
including sign, decimal point, exponent marker/sign, and digits. Both integer
and float callbacks enforce it before host conversion; the exact limit is
accepted and the first character above it is rejected.
Integer conversion is deliberately chunked into at most 18-digit calls to
`int()`, so CPython's process-wide decimal-string digit limit cannot reject an
LM9A token that passed the 1,024-character gate. Product validation still
rejects the resulting unsafe integer; parser acceptance grants no semantic
validity.

Implement `snapshot_json_tree` as two independent iterative, non-recursive
freezes of the caller value. Each freeze copies a mapping through one bounded
`tuple(mapping.items())`; mapping exceptions, duplicate/non-string keys, or
unsupported host values return the exact snapshot error rather than retaining
the mapping. Object keys traverse in `utf16_sort_key` order and arrays in index
order. Record every source container identity within each pass and reject any
repeat, including cycles. Arrays must be `list`; tuple is not a JSON array.
Accepted scalars are exactly `None`, `bool`, `str`, `int`, and finite `float`,
with `bool` handled before `int`. Reject surrogate strings, and reject an
integer when `float(value)` raises `OverflowError` or is not finite. Finite
integers outside the product-safe range remain legal here so embedded JSON
Schemas preserve the Section 9 exception.

Compare the two complete frozen values and their canonical fingerprints. Any
difference is `validation_input_snapshot_unstable_mapping`; accept only the
second result. This catches custom mappings or concurrent caller mutation that
produce different observations during preflight. Mutation after the second
freeze is harmless because no caller-owned container is retained.

The result contains only immutable tagged object/array tuples and scalars. Its
fingerprint is `canonical_sha256` of that frozen value's exact thawed JSON tree.
`thaw()` builds a new plain `dict`/`list` tree iteratively on every call. The
snapshot never exposes internal mutable storage, and no validator phase receives
the caller's mapping or another phase's thawed tree.

Implement `_serialize_number`, `_serialize_string`, and `_serialize_value` in the same module. `_serialize_number` must pass every committed Appendix B vector; do not delegate whole-value serialization to `json.dumps`. `_serialize_string` may use `json.dumps(value, ensure_ascii=False, allow_nan=False)` only for JSON string escaping after `_reject_surrogate_string`. `_serialize_value` must sort object keys with `utf16_sort_key`, handle `bool` before `int`, serialize finite `float` through `_serialize_number`, and reject unsupported Python types.

Use this number-formatting algorithm, whose committed vector gate is the
acceptance authority:

```python
def _serialize_number(value: int | float) -> str:
    if isinstance(value, bool):
        raise CanonicalJsonError("invalid_json_number", "Boolean is not a number here.")
    if isinstance(value, int):
        if -9007199254740991 <= value <= 9007199254740991:
            return str(value)
        try:
            value = float(value)
        except OverflowError as exc:
            raise CanonicalJsonError("nonfinite_json_number", "Integer exceeds IEEE 754 range.") from exc
    if not math.isfinite(value):
        raise CanonicalJsonError("nonfinite_json_number", repr(value))
    if value == 0.0:
        return "0"

    rendered = repr(value).lower()
    magnitude = abs(value)
    if 1e-6 <= magnitude < 1e21:
        fixed = format(Decimal(rendered), "f")
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        return fixed

    if "e" not in rendered:
        sign = "-" if rendered.startswith("-") else ""
        digits = rendered.lstrip("-").replace(".", "").lstrip("0")
        exponent = len(rendered.lstrip("-").split(".", 1)[0]) - 1
        coefficient = digits[0] + (("." + digits[1:]) if len(digits) > 1 else "")
        return f"{sign}{coefficient}e{exponent:+d}"

    coefficient, exponent_text = rendered.split("e", 1)
    exponent = int(exponent_text)
    coefficient = coefficient.rstrip("0").rstrip(".")
    return f"{coefficient}e{exponent:+d}"
```

Do not accept this code on inspection alone. The entire Appendix B fixture must
pass, because that fixture catches threshold, shortest-round-trip, negative
zero, and exponent-format differences between Python and ECMAScript.

Use these final wrappers:

```python
def canonical_json_bytes(value: Any) -> bytes:
    validate_json_tree(value)
    return _serialize_value(value).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256_prefixed(canonical_json_bytes(value))


def typed_value_fingerprint(typed_value: Mapping[str, Any]) -> str:
    return canonical_sha256(dict(typed_value))
```

Implement `compare_compound` explicitly rather than relying on host tuple comparison: compare integers numerically, strings through `utf16_sort_key`, and lists element-by-element with shorter-prefix-first behavior. Reject unsupported key component types.

- [ ] **Step 5: Run canonicalization tests and inspect all vectors**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_canonical.py -q
```

Expected: all tests pass, including all 24 finite Appendix B vectors.

- [ ] **Step 6: Commit the canonicalization boundary**

```powershell
git add mcp_server/src/rook/agent/planner_graph_recipe_canonical.py `
  mcp_server/tests/fixtures/lm9a/rfc8785_number_vectors.json `
  mcp_server/tests/test_planner_graph_recipe_canonical.py
git commit -m "feat(lm9a): add exact canonical json boundary"
```

---

### Task 2: Closed Schema Catalog And Direct Schema Runtime Dependencies

**Files:**
- Modify: `mcp_server/pyproject.toml`
- Modify: `mcp_server/uv.lock`
- Create: `mcp_server/src/rook/agent/planner_graph_recipe_schemas.py`
- Create: `mcp_server/tests/lm9a_contract_factory.py`
- Create: `mcp_server/tests/test_planner_graph_recipe_schemas.py`

**Interfaces:**
- Consumes: parsed JSON mappings and registered payload schemas.
- Produces:
  - `SCHEMA_DIALECT`
  - schema constants for every LM9A product and report artifact
  - internal `VALIDATION_INPUT_ENVELOPE_SCHEMA`
  - `schema_for(schema_id: str) -> Mapping[str, Any]`
  - `validate_closed_payload(payload: Any, schema_id: str) -> tuple[SchemaIssue, ...]`
  - `validate_registered_schema_document(schema_document: Mapping[str, Any]) -> tuple[SchemaIssue, ...]`
  - `validate_registered_payload(payload: Any, schema_document: Mapping[str, Any]) -> tuple[SchemaIssue, ...]`
  - `validate_product_number_tree(payload: Any, schema_id: str) -> tuple[SchemaIssue, ...]`
  - `normalize_product_payload(payload: Any, schema_id: str) -> Any`
  - `semantic_reference_sort_key(reference: Mapping[str, Any]) -> tuple[Any, ...]`
  - `SET_SORT_RULES`

- [ ] **Step 1: Promote the already-resolved schema runtime packages to direct ownership**

Add this dependency to `mcp_server/pyproject.toml`:

```toml
    "jsonschema==4.26.0",
    "jsonschema-specifications==2025.9.1",
    "referencing==0.37.0",
```

Then run:

```powershell
uv lock --project mcp_server
uv tree --project mcp_server --invert --package jsonschema
uv tree --project mcp_server --invert --package jsonschema-specifications
uv tree --project mcp_server --invert --package referencing
```

Expected: `jsonschema v4.26.0`, `jsonschema-specifications v2025.9.1`, and
`referencing v0.37.0` remain the resolved packages and `rook-mcp` now owns
direct edges to all three. Inspect
`mcp_server/uv.lock`; no second JSON Schema implementation or JCS package may
appear.

- [ ] **Step 2: Write schema-catalog and closed-object tests**

```python
from jsonschema import Draft202012Validator

from rook.agent.planner_graph_recipe_schemas import (
    PRODUCT_SCHEMAS,
    RECIPE_SCHEMA,
    VALIDATION_INPUT_SCHEMA,
    VALIDATION_REPORT_SCHEMA,
    schema_for,
)


def test_every_product_schema_is_valid_draft_2020_12():
    for schema in PRODUCT_SCHEMAS.values():
        Draft202012Validator.check_schema(schema)


def test_public_schema_catalog_contains_exact_lm9a_contracts():
    assert set(PRODUCT_SCHEMAS) == {
        "rook.planner_graph_recipe:v1",
        "rook.planner_graph_recipe_validation_input:v1",
        "rook.planner_graph_recipe_validation_report:v1",
        "rook.planner_task_envelope:v1",
        "rook.environment_snapshot:v1",
        "rook.payload_schema_registry:v1",
        "rook.planning_policy:v1",
        "rook.planner_assumption_confirmation_receipt:v1",
        "rook.environment_capability_registry:v1",
        "rook.semantic_authority_code_vocabulary:v1",
        "rook.semantic_capability_code_vocabulary:v1",
        "rook.worker_slot_code_vocabulary:v1",
        "rook.semantic_materiality_code_vocabulary:v1",
        "rook.semantic_value_schema_registry:v1",
    }


def test_unknown_properties_fail_at_top_level_and_nested_level():
    recipe, validation_input = minimal_valid_contract()
    recipe["unexpected"] = True
    assert issue_codes(recipe, RECIPE_SCHEMA) == {"additionalProperties"}

    recipe, validation_input = minimal_valid_contract()
    recipe["goal"]["unexpected"] = True
    assert issue_codes(recipe, RECIPE_SCHEMA) == {"additionalProperties"}


def test_schema_messages_are_bounded_and_hash_hostile_detail():
    recipe, _ = minimal_valid_contract()
    hostile = "x" * 100_000
    recipe[hostile] = True
    issues = validate_closed_payload(recipe, recipe["schema"])
    assert issues
    assert all(len(issue.message) <= 512 for issue in issues)
    assert all(hostile not in issue.message for issue in issues)


@pytest.mark.parametrize(
    ("keyword", "value", "expected_code"),
    [
        ("$ref", "https://example.test/schema", "payload_schema_remote_ref"),
        ("$dynamicRef", "#/$defs/local", "payload_schema_dynamic_ref_forbidden"),
        ("$recursiveRef", "#", "payload_schema_recursive_ref_forbidden"),
        ("$id", "https://example.test/base", "payload_schema_identifier_forbidden"),
        ("$anchor", "local", "payload_schema_anchor_forbidden"),
        ("$dynamicAnchor", "local", "payload_schema_dynamic_anchor_forbidden"),
    ],
)
def test_registered_schema_reference_surface_is_closed(keyword, value, expected_code):
    schema = {"$schema": SCHEMA_DIALECT, "type": "object", keyword: value}
    assert {issue.code for issue in validate_registered_schema_document(schema)} == {
        expected_code
    }


def test_set_order_normalization_is_deterministic_but_ordered_arrays_remain_material():
    left, _ = minimal_valid_contract()
    right = copy.deepcopy(left)
    right["maintains"][0]["source_refs"] = list(
        reversed(right["maintains"][0]["source_refs"])
    )
    assert normalize_product_payload(left, left["schema"]) == (
        normalize_product_payload(right, right["schema"])
    )

    left["goal"]["statement"] = "Create output A.\nThen preserve output B."
    right["goal"]["statement"] = "Then preserve output B.\nCreate output A."
    assert normalize_product_payload(left, left["schema"]) != (
        normalize_product_payload(right, right["schema"])
    )


@pytest.mark.parametrize("value", [1.5, -(2**53), 2**53])
def test_product_number_tree_rejects_float_and_unsafe_integer(value):
    recipe, _ = minimal_valid_contract()
    recipe["goal"]["unexpected_numeric_probe"] = value
    issues = validate_product_number_tree(recipe, recipe["schema"])
    assert {issue.code for issue in issues} & {
        "non_integer_product_number",
        "unsafe_json_integer",
    }


def test_embedded_schema_document_is_the_only_float_exception():
    _, validation_input = minimal_valid_contract()
    document = validation_input["validation_context"]["payload_schema_registry"]
    document["entries"][0]["schema_document"]["multipleOf"] = 0.5
    document["entries"][0]["schema_document"]["maximum"] = 9007199254740992
    assert validate_product_number_tree(document, document["schema"]) == ()
    first = canonical_sha256(document)
    second = canonical_sha256(copy.deepcopy(document))
    assert first == second
```

- [ ] **Step 3: Run the schema tests to establish the red state**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_schemas.py -q
```

Expected: import failure for `planner_graph_recipe_schemas`.

- [ ] **Step 4: Implement the closed schema catalog**

Start the module with exact schema/version constants and one closed-object helper:

```python
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry

from rook.agent.planner_graph_recipe_canonical import bounded_message


SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
MACHINE_ID_PATTERN = r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
DECIMAL_PATTERN = r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"
SAFE_INTEGER_MIN = -9007199254740991
SAFE_INTEGER_MAX = 9007199254740991


@dataclass(frozen=True)
class SchemaIssue:
    code: str
    path: str
    message: str


def closed_object(
    *,
    required: tuple[str, ...],
    properties: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(required),
        "properties": dict(properties),
        "additionalProperties": False,
    }
```

Define reusable `$defs` for machine IDs, hashes, timestamps, exact RFC 6901 pointers, semantic prose, typed values, the ten-variant semantic-reference union, common clauses, assumptions, derived facts, unresolved intent, shape entries, capability entries, worker-slot entries, all four report descriptors, diagnostics, blockers, and phase rows.

Set `maxLength: 512` on diagnostic and compile-blocker `message` fields and on
any raw-ingress error message copied into a report. Constructors in
`planner_graph_recipe_report.py` reject over-limit messages rather than
truncating a second time; all variable-detail messages are constructed with
`bounded_message` at their originating boundary.

The catalog must encode these exact top-level shapes:

| Schema | Required top-level fields |
|---|---|
| recipe | `schema`, `source_task`, `authority_artifacts`, `goal`, `requires`, `maintains`, `assumptions`, `derived_facts`, `unresolved_intent`, `invariants`, `shape`, `required_capabilities`, `worker_slots`, `recipe_fingerprint` |
| validation input | `schema`, `task_envelope`, `authority_artifacts`, `validation_context` |
| task envelope | `schema`, `artifact_id`, `task_session_id`, `payload_schema`, `payload_schema_fingerprint`, `payload`, `value_bindings`, `issued_at`, `artifact_fingerprint` |
| environment snapshot | `schema`, `artifact_id`, `environment_session_id`, `payload_schema`, `payload_schema_fingerprint`, `payload`, `value_bindings`, `observed_at`, `expires_at`, `issuer`, `artifact_fingerprint` |
| validation report | every field in spec Section 8, including `validation_input_snapshot_fingerprint`, explicit companion descriptors, `phases`, `diagnostics`, `compile_blockers`, `valid`, `compile_ready`, and `report_fingerprint` |

Encode the full closed companion/vocabulary shapes from spec Sections 4.2 through 4.7 and the full recipe shapes from Sections 6.1 through 6.11. Use local `$defs` only. Do not permit remote `$ref`, URI-fragment semantic pointers, unknown receipt kinds, or non-integer product JSON numbers.

Implement schema validation with stable RFC 6901 issue paths:

```python
def validate_closed_payload(payload: Any, schema_id: str) -> tuple[SchemaIssue, ...]:
    validator = Draft202012Validator(schema_for(schema_id))
    issues = []
    for error in validator.iter_errors(payload):
        pointer = "".join(
            "/" + str(part).replace("~", "~0").replace("/", "~1")
            for part in error.absolute_path
        )
        issues.append(
            SchemaIssue(
                error.validator or "schema",
                pointer,
                bounded_message("Schema validation failed.", error.message),
            )
        )
    return tuple(sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message)))
```

`VALIDATION_INPUT_SCHEMA` remains the complete recursively closed product
schema used by catalog and artifact-conformance tests. The public validator does
not run that aggregate schema in the recipe `schema` phase. Task 4 uses a
separate internal `VALIDATION_INPUT_ENVELOPE_SCHEMA` to stage ownership:

- it closes the validation-input top level and the mechanical
  `validation_context` fields and collection containers;
- companion-valued positions are constrained to object/array container shapes
  but remain opaque to this envelope schema;
- each contained task, authority, environment, policy, registry, and vocabulary
  companion is then validated independently under its exact product schema.

This two-stage validation is collectively equivalent to the complete product
schema while preserving deterministic phase ownership. Envelope errors become
`companion_artifacts / validation_input_schema_failed`; errors inside a
companion become
`companion_artifacts / companion_schema_validation_failed`. The recipe
`schema` phase validates only the exact recipe bytes and
`rook.planner_graph_recipe:v1` payload.

For registered payload schemas, require exact Draft 2020-12 and run
`Draft202012Validator.check_schema`. The v1 reference surface is closed:

- `$ref` is the only allowed reference-bearing keyword and must be `#` or a
  same-document RFC 6901 fragment beginning `#/`;
- `$dynamicRef` and `$recursiveRef` are forbidden;
- `$id`, `$anchor`, and `$dynamicAnchor` are forbidden so a schema cannot alter
  base or anchor resolution;
- `$schema` must equal the exact Draft 2020-12 dialect;
- validation instantiates `Draft202012Validator(schema, registry=Registry())`,
  whose registry has no retrieval callback or preloaded remote resources.

Catch `referencing.exceptions.Unresolvable` and convert it to the deterministic
`payload_schema_reference_unresolvable` diagnostic through `bounded_message`.
Never expose the raw URI or library exception text in the report.

`validate_product_number_tree` walks every product artifact after parsing. It
rejects non-integer Python `float` values and integers outside the interoperable
safe range at every path except values nested under a payload-schema registry
entry’s `schema_document`. That exception permits the complete finite RFC 8785
number domain, including integer-form values outside the product safe range;
nonfinite numbers were already rejected by raw ingress.

- [ ] **Step 5: Implement schema-directed normalization and the exhaustive set table**

`normalize_product_payload` deep-copies the schema-valid payload, normalizes only
schema-designated semantic prose with `normalize_semantic_prose`, preserves JSON
Pointers and exact property names, rejects duplicate stable identities before
sorting, and applies only the set rules below. Arrays absent from this table
retain received order:

```python
SET_SORT_RULES = {
    "authority_artifacts": "artifact_id",
    "environment_snapshots": "artifact_id",
    "policy_registries": "artifact_id",
    "value_bindings": "binding_id",
    "payload_schema_entries": "schema_id",
    "capability_registry_entries": "capability_code",
    "vocabulary_entries": "code_or_schema",
    "requires": "clause_id",
    "maintains": "clause_id",
    "invariants": "clause_id",
    "canonicalization": "clause_id",
    "postconditions": "clause_id",
    "semantic_references": "semantic_reference",
    "goal_projection_ids": "machine_id",
    "clause_id_lists": "machine_id",
    "assumptions": "assumption_id",
    "assumption_affects": "machine_id",
    "derived_facts": "derived_fact_id",
    "unresolved_intent": "intent_id",
    "unresolved_enum_lists": "machine_id",
    "shape_entries": "shape_id",
    "required_capability_entries": "capability_id",
    "worker_slot_entries": "worker_slot_id",
    "vocabulary_closed_lists": "machine_id",
    "implementation_refs": "utf16_string",
    "report_vocabularies": "schema_and_version",
    "recipe_binding_paths": "utf16_string",
    "related_paths": "utf16_string",
}
```

Associate each rule with exact schema locations, including all aliases listed in
spec Section 9. Do not dispatch by field name alone: for example, generic arrays
named `entries` use different keys in payload-schema, capability, vocabulary,
required-capability, and worker-slot schemas. Encode the association as schema
annotations or a `(schema_id, RFC6901 path-pattern)` table and add a test that
every Section 9 collection is represented exactly once.

`semantic_reference_sort_key` uses rank `0..9` and the exact variant tuple from
spec Section 9. Duplicate semantic-reference tuples fail before sorting.

- [ ] **Step 6: Create the domain-neutral contract factory**

`mcp_server/tests/lm9a_contract_factory.py` must expose:

- `minimal_valid_contract() -> tuple[dict[str, Any], dict[str, Any]]`
- `stamp_fingerprint(payload: dict[str, Any], field: str) -> dict[str, Any]`
- `raw_recipe_bytes(recipe: Mapping[str, Any]) -> bytes`
- `issue_codes(payload: Any, schema: Mapping[str, Any]) -> set[str]`
- `diagnostic_codes(result: Any) -> set[str]`

`stamp_fingerprint` deep-copies the input, inserts a syntactically valid
all-zero provisional hash when the required terminal field is absent, validates
and normalizes the complete object under its product schema, removes only the
named terminal field from the normalized projection, computes
`canonical_sha256`, and returns a second deep copy carrying that digest.
`raw_recipe_bytes` uses normal
JSON serialization with `ensure_ascii=False` because raw ingress identity is
intentionally distinct from canonical identity. `minimal_valid_contract`
returns one neutral layer-maintenance recipe and the complete companion input
needed to validate it; it must stamp companions from the leaves upward so no
claimed fingerprint is stale. Its maintained clause has at least two direct
source references so set-order tests exercise a real permutation.

Use neutral identifiers such as `maintained.output`, `capability.manage_document_layers`, and `fixture-task-session`. The helper may compute fingerprints with Task 1’s canonicalizer. It must not import validator orchestration from later tasks.

- [ ] **Step 7: Run schema and canonicalization tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_canonical.py `
  mcp_server/tests/test_planner_graph_recipe_schemas.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit the schema boundary**

```powershell
git add mcp_server/pyproject.toml mcp_server/uv.lock `
  mcp_server/src/rook/agent/planner_graph_recipe_schemas.py `
  mcp_server/tests/lm9a_contract_factory.py `
  mcp_server/tests/test_planner_graph_recipe_schemas.py
git commit -m "feat(lm9a): define closed recipe schemas"
```

---

### Task 3: Deterministic Diagnostics, Phase Status, And Report Descriptors

**Files:**
- Create: `mcp_server/src/rook/agent/planner_graph_recipe_report.py`
- Create: `mcp_server/tests/test_planner_graph_recipe_report.py`

**Interfaces:**
- Consumes: phase-local diagnostics/blockers and companion descriptor payloads.
- Produces:
  - `Diagnostic`
  - `CompileBlocker`
  - `PhaseIssues(diagnostics: tuple[Diagnostic, ...], blockers: tuple[CompileBlocker, ...])`
  - `ValidationLedger`
  - `PHASE_ORDER`, `PHASE_DEPENDENCIES`
  - `derive_phase_rows(ledger: ValidationLedger) -> tuple[Mapping[str, Any], ...]`
  - `sorted_diagnostics(issues: Iterable[Diagnostic]) -> tuple[Mapping[str, Any], ...]`
  - `sorted_blockers(issues: Iterable[CompileBlocker]) -> tuple[Mapping[str, Any], ...]`
  - descriptor constructors for recipe authority, validation artifacts, registries, and vocabularies.

- [ ] **Step 1: Write issue-ordering and phase-derivation tests**

```python
def test_related_paths_use_lexicographic_shorter_prefix_first():
    issues = [
        diagnostic("schema", "x", related_paths=("/a", "/b")),
        diagnostic("schema", "x", related_paths=("/a",)),
    ]
    assert [row["related_paths"] for row in sorted_diagnostics(issues)] == [
        ["/a"],
        ["/a", "/b"],
    ]


def test_blocked_dependency_does_not_suppress_downstream_phase():
    ledger = ValidationLedger()
    ledger.add_blocker(blocker("assumptions", "confirmation_required"))
    rows = {row["phase"]: row for row in derive_phase_rows(ledger)}
    assert rows["assumptions"]["status"] == "blocked"
    assert rows["unresolved_intent"]["status"] == "passed"
    assert rows["readiness"]["status"] == "blocked"


def test_failed_dependency_marks_downstream_not_evaluated():
    ledger = ValidationLedger()
    ledger.add_diagnostic(diagnostic("companion_artifacts", "invalid_companion"))
    rows = {row["phase"]: row for row in derive_phase_rows(ledger)}
    assert rows["provenance"]["status"] == "not_evaluated"
    assert rows["readiness"]["status"] == "not_evaluated"


def test_companion_phase_remains_independent_when_recipe_schema_fails():
    ledger = ValidationLedger()
    ledger.add_diagnostic(diagnostic("schema", "schema_validation_failed"))
    rows = {row["phase"]: row for row in derive_phase_rows(ledger)}
    assert rows["schema"]["status"] == "failed"
    assert rows["companion_artifacts"]["status"] == "passed"
    assert rows["fingerprint"]["status"] == "not_evaluated"
    assert rows["clause_graph"]["status"] == "not_evaluated"


def test_same_issue_cannot_be_diagnostic_and_blocker():
    ledger = ValidationLedger()
    ledger.add_diagnostic(diagnostic("assumptions", "policy_prohibited"))
    with pytest.raises(ValueError, match="issue_classification_conflict"):
        ledger.add_blocker(blocker("assumptions", "policy_prohibited"))


def test_report_issue_records_reject_unbounded_messages():
    with pytest.raises(ValueError, match="evidence_message_too_long"):
        diagnostic("schema", "invalid_schema", message="x" * 513)
```

- [ ] **Step 2: Run the report tests to establish the red state**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_report.py -q
```

Expected: import failure for `planner_graph_recipe_report`.

- [ ] **Step 3: Implement issue records and the fixed phase graph**

```python
@dataclass(frozen=True)
class Diagnostic:
    severity: str
    phase: str
    code: str
    subject_id: str
    path: str
    related_paths: tuple[str, ...]
    message: str

    def __post_init__(self) -> None:
        if len(self.message) > MAX_EVIDENCE_MESSAGE_CHARS:
            raise ValueError("evidence_message_too_long")


@dataclass(frozen=True)
class CompileBlocker:
    phase: str
    code: str
    subject_id: str
    path: str
    related_paths: tuple[str, ...]
    message: str

    def __post_init__(self) -> None:
        if len(self.message) > MAX_EVIDENCE_MESSAGE_CHARS:
            raise ValueError("evidence_message_too_long")


@dataclass(frozen=True)
class PhaseIssues:
    diagnostics: tuple[Diagnostic, ...] = ()
    blockers: tuple[CompileBlocker, ...] = ()


PHASE_ORDER = (
    "schema",
    "fingerprint",
    "companion_artifacts",
    "provenance",
    "clause_graph",
    "derived_facts",
    "assumptions",
    "unresolved_intent",
    "shape",
    "capabilities",
    "worker_slots",
    "readiness",
)

PHASE_DEPENDENCIES = {
    "schema": (),
    "fingerprint": ("schema",),
    "companion_artifacts": (),
    "provenance": ("companion_artifacts",),
    "clause_graph": ("schema", "companion_artifacts"),
    "derived_facts": ("companion_artifacts", "provenance", "clause_graph"),
    "assumptions": ("companion_artifacts", "provenance", "clause_graph"),
    "unresolved_intent": (
        "companion_artifacts", "provenance", "clause_graph", "assumptions"
    ),
    "shape": ("companion_artifacts", "clause_graph"),
    "capabilities": ("companion_artifacts", "clause_graph", "shape"),
    "worker_slots": ("companion_artifacts", "clause_graph", "shape"),
    "readiness": PHASE_ORDER[:-1],
}
```

Use frozen dataclasses with exactly the closed fields from spec Section 8.5. `Diagnostic.severity` is `error | warning | information`; blockers have no severity. `ValidationLedger` stores each issue under a stable identity `(phase, code, subject_id, path, related_paths)` and rejects an identity being added to both collections.

Sort with Task 1’s explicit comparator and these tuples:

```text
diagnostic: (phase_rank, severity_rank, code, subject_id, path, related_paths, message)
blocker:    (phase_rank, code, subject_id, path, related_paths, message)
```

Derive phase status exactly:

```text
dependency failed/not_evaluated -> not_evaluated
evaluated + error diagnostic    -> failed
evaluated + no error + blocker  -> blocked
otherwise                       -> passed
```

Warnings and informational diagnostics do not fail a phase. A blocked dependency remains evaluable.
`readiness` is the one aggregate phase: when any compile blocker exists anywhere
in the ledger, its status is `blocked` without copying that blocker into the
readiness phase.

- [ ] **Step 4: Add closed descriptor constructors**

Implement constructors whose returned key sets exactly match spec Sections 8.2 and 8.3:

- `recipe_authority_descriptor`, accepting the discriminator, stable artifact
  identity, exact schema, recipe/companion/computed fingerprints, both nullable
  session fields, and the three derived status fields.
- `validation_artifact_descriptor`, accepting the validation-only artifact
  discriminator, stable identity, exact schema, companion/computed
  fingerprints, session fields, and derived statuses; it has no recipe-claimed
  fingerprint parameter.
- `registry_descriptor`, accepting fixed registry identity/kind/schema,
  companion/computed fingerprints, registry session, and derived statuses.
- `vocabulary_descriptor`, accepting exact schema/version, sorted binding paths,
  nullable recipe-claimed fingerprint, companion/computed fingerprints, entry
  count, and validation status.
- `validation_context_projection(report: Mapping[str, Any]) -> dict[str, Any]`.

Fixed-position task, registry, and vocabulary constructors must be able to emit
a conforming failed/not-evaluated descriptor from a present but malformed shell:
use the slot's fixed discriminator, stable identity, and expected schema; use
explicit `null` for unrecoverable evidence fields. Variable-list items without a
recoverable stable identity produce no descriptor row and remain bound through
the snapshot fingerprint plus their path-addressed diagnostic.

The projection must include `validation_input_snapshot_fingerprint`, omit
derived status fields, and preserve explicit `null` computed fingerprints. Add
tests that changing `session_status` does not move the context projection while
changing the snapshot fingerprint, a trusted session ID, or a computed
companion fingerprint does.

- [ ] **Step 5: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_report.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit report primitives**

```powershell
git add mcp_server/src/rook/agent/planner_graph_recipe_report.py `
  mcp_server/tests/test_planner_graph_recipe_report.py
git commit -m "feat(lm9a): add deterministic validation reporting"
```

---

### Task 4: Companion Authority, Payload Schemas, And Reference Resolution

**Files:**
- Create: `mcp_server/src/rook/agent/planner_graph_recipe_authority.py`
- Create: `mcp_server/tests/test_planner_graph_recipe_authority.py`
- Modify: `mcp_server/tests/lm9a_contract_factory.py`

**Interfaces:**
- Consumes: the immutable validation-input snapshot, its trusted time/session
  projection, and an optional schema-valid recipe payload. Companion validation
  does not depend on recipe schema success.
- Produces:
  - `CompanionIndex`
  - `CompanionValidationResult(index, source_task_descriptor, authority_descriptors, context_descriptors, vocabulary_descriptors, diagnostics)`
  - `validate_companions(recipe_or_none, validation_input_snapshot) -> CompanionValidationResult`
  - `validate_validation_input_structure(validation_input) -> PhaseIssues`
  - `resolve_semantic_reference(reference, index) -> ResolvedReference`
  - `resolve_json_pointer(document, pointer) -> Any`
  - `exact_decimal(value: str) -> Decimal`

- [ ] **Step 1: Write companion and reference tests**

Cover exact positive and negative boundaries:

```python
def test_artifact_value_resolves_payload_relative_through_one_binding():
    recipe, validation_input = minimal_valid_contract()
    result = validate_companions(recipe, snapshot_json_tree(validation_input))
    resolved = resolve_semantic_reference(
        {"kind": "artifact_value", "artifact_id": "task_envelope", "json_pointer": "/facts/name"},
        result.index,
    )
    assert resolved.authority_kind == "user_fact"
    assert resolved.value == "Analysis"


def test_duplicate_binding_pointer_is_invalid_even_with_distinct_ids():
    recipe, validation_input = minimal_valid_contract()
    bindings = validation_input["task_envelope"]["value_bindings"]
    bindings.append({**bindings[0], "binding_id": "task-value.duplicate"})
    result = validate_companions(recipe, snapshot_json_tree(validation_input))
    assert "duplicate_value_binding_pointer" in diagnostic_codes(result)


def test_unknown_validation_input_field_is_an_envelope_error():
    recipe, validation_input = minimal_valid_contract()
    validation_input["unknown"] = True
    result = validate_companions(recipe, snapshot_json_tree(validation_input))
    assert diagnostic_codes(result) == {"validation_input_schema_failed"}


def test_unknown_nested_task_field_is_a_companion_schema_error():
    recipe, validation_input = minimal_valid_contract()
    validation_input["task_envelope"]["unknown"] = True
    result = validate_companions(recipe, snapshot_json_tree(validation_input))
    assert diagnostic_codes(result) == {"companion_schema_validation_failed"}


@pytest.mark.parametrize(
    ("pointer", "expected_code"),
    [
        ("", "semantic_pointer_empty"),
        ("#/facts/name", "json_pointer_uri_fragment_forbidden"),
        ("/facts/~2name", "json_pointer_escape_invalid"),
    ],
)
def test_semantic_pointer_forms_fail_closed(pointer, expected_code):
    recipe, validation_input = minimal_valid_contract()
    result = validate_companions(recipe, snapshot_json_tree(validation_input))
    reference = {
        **recipe["maintains"][0]["source_refs"][0],
        "json_pointer": pointer,
    }
    with pytest.raises(SemanticReferenceError, match=expected_code):
        resolve_semantic_reference(reference, result.index)


def test_present_but_malformed_task_shell_still_yields_closed_source_descriptor():
    recipe, validation_input = minimal_valid_contract()
    validation_input["task_envelope"] = {}
    result = validate_companions(recipe, snapshot_json_tree(validation_input))
    assert diagnostic_codes(result) == {"companion_schema_validation_failed"}
    assert result.source_task_descriptor == {
        "descriptor_kind": "recipe_authority",
        "artifact_id": "task_envelope",
        "artifact_kind": "task_envelope",
        "schema": "rook.planner_task_envelope:v1",
        "recipe_claimed_fingerprint": recipe["source_task"]["fingerprint"],
        "companion_claimed_fingerprint": None,
        "computed_fingerprint": None,
        "task_session_id": None,
        "environment_session_id": None,
        "session_status": "not_evaluated",
        "freshness_status": "not_evaluated",
        "validation_status": "failed",
    }


def test_unclassifiable_variable_companion_is_diagnosed_without_fake_descriptor():
    recipe, validation_input = minimal_valid_contract()
    validation_input["authority_artifacts"].append({"unknown": True})
    snapshot = snapshot_json_tree(validation_input)
    result = validate_companions(recipe, snapshot)
    assert "companion_schema_validation_failed" in diagnostic_codes(result)
    assert len(result.authority_descriptors) == 0
    assert snapshot.fingerprint.startswith("sha256:")
```

Task 5 repeats these mutations through the public validator and asserts
`provenance / <expected_code>`. Task 4 proves the authority helper's exact error
surface only; companion validation does not scan recipe clauses or assign
semantic-reference errors to `companion_artifacts`.

Add the remaining cases as explicit mutation/expected-result rows:

| Mutation | Exact expected diagnostic/blocker |
|---|---|
| payload schema contains `https://example.test/remote.json` `$ref` | `companion_artifacts / payload_schema_remote_ref` diagnostic |
| task `payload_schema_fingerprint` differs from registry entry | `companion_artifacts / payload_schema_fingerprint_mismatch` diagnostic |
| environment `expires_at` precedes trusted `evaluated_at` | `companion_artifacts / environment_snapshot_expired` diagnostic |
| environment session differs from trusted context | `companion_artifacts / environment_session_mismatch` diagnostic |
| authority companion uses a reserved target/privileged receipt schema | `companion_artifacts / deferred_receipt_kind` diagnostic |
| required capability registry row says `unavailable` | no authority diagnostic; later `capabilities / capability_unavailable` blocker |

- [ ] **Step 2: Run authority tests to establish the red state**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_authority.py -q
```

Expected: import failure for `planner_graph_recipe_authority`.

- [ ] **Step 3: Implement staged validation-input ownership, RFC 6901 resolution, and companion indexing**

`validate_companions` calls `validation_input_snapshot.thaw()` once for its own
private tree; it never receives the caller mapping or another phase's tree. The
snapshot has already fenced depth, container identity, Unicode, host types, and
the finite JCS numeric domain. Companion validation begins with
`VALIDATION_INPUT_ENVELOPE_SCHEMA`; envelope failures are bounded and
normalized to `validation_input_schema_failed`. Only after that
passes does it validate each contained companion under its exact product
schema, normalizing those failures to `companion_schema_validation_failed`.
Do not index, resolve references, recompute companion fingerprints, or derive
freshness/session status for a structurally invalid companion. Independent
well-formed companions may still receive diagnostics in the same evaluated
phase; do not manufacture diagnostics that require fields absent from the
malformed companion.

`resolve_json_pointer` must accept only the empty diagnostic root pointer or nonempty `/...` semantic pointers as directed by the caller, decode only `~0` and `~1`, preserve exact property-name Unicode, resolve mapping keys exactly, and resolve list indices only from canonical unsigned decimal tokens (`0` or a nonzero digit followed by digits). The semantic-reference validator still requires the pointer to equal exactly one declared value binding before that resolved value gains authority.

`CompanionIndex` must maintain separate mappings for:

```python
@dataclass(frozen=True)
class CompanionIndex:
    recipe_authorities: Mapping[str, Mapping[str, Any]]
    validation_artifacts: Mapping[str, Mapping[str, Any]]
    payload_schemas: Mapping[str, Mapping[str, Any]]
    policies: Mapping[str, Mapping[str, Any]]
    capability_registry: Mapping[str, Any]
    vocabularies: Mapping[tuple[str, str], Mapping[str, Any]]
    value_bindings: Mapping[tuple[str, str], Mapping[str, Any]]
```

Reject duplicate artifact IDs across recipe-bound and validation-context companions before indexing. Recompute every companion fingerprint by removing only its terminal fingerprint field, schema-normalizing, and using `canonical_sha256`.

Treat placement in the trusted validation-input companion channel as the trust
boundary for LM9A v1. Issuer fields are checked against the closed companion
kind and bound into fingerprints; the recipe cannot promote an untrusted object
by labeling it. Do not invent a new issuer registry or signature protocol in
this slice.

- [ ] **Step 4: Validate registered payload schemas and payload bindings**

For each task/environment companion:

1. Find exactly one payload-schema registry entry by `schema_id`.
2. Recompute and compare `schema_fingerprint`.
3. verify Draft 2020-12 and local-only `$ref` use.
4. Validate `payload` against the exact schema document.
5. Require unique nonempty binding pointers.
6. Resolve each pointer inside `payload`.
7. Validate the resolved value under the registered semantic value schema.
8. Recompute `{schema: value_schema, value: resolved_value}` and compare `typed_value_fingerprint`.

Use trusted `validation_context.evaluated_at` and trusted session fields for freshness/session comparisons. A companion’s own repeated session value is evidence to compare, never freshness authority.

- [ ] **Step 5: Validate policy, capability, and vocabulary registries**

Require all five exact v1 vocabulary companions and minimum entries from spec Section 4.7. Reject duplicate/unknown codes and fingerprint mismatches. Validate policy rules as a stable map keyed by matching `rule_id`; reject overlaps for one semantic key and exact scope. Keep capability availability separate from semantic authority.

- [ ] **Step 6: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_canonical.py `
  mcp_server/tests/test_planner_graph_recipe_schemas.py `
  mcp_server/tests/test_planner_graph_recipe_report.py `
  mcp_server/tests/test_planner_graph_recipe_authority.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the authority boundary**

```powershell
git add mcp_server/src/rook/agent/planner_graph_recipe_authority.py `
  mcp_server/tests/lm9a_contract_factory.py `
  mcp_server/tests/test_planner_graph_recipe_authority.py
git commit -m "feat(lm9a): validate recipe authority companions"
```

---

### Task 5: Clause Graph, Provenance Coverage, And Derived Facts

**Files:**
- Create: `mcp_server/src/rook/agent/planner_graph_recipe_semantics.py`
- Create: `mcp_server/tests/test_planner_graph_recipe_semantics.py`
- Modify: `mcp_server/tests/lm9a_contract_factory.py`

**Interfaces:**
- Consumes: schema-valid recipe plus validated `CompanionIndex`.
- Produces:
  - `RecipeSemanticIndex`
  - `index_recipe_semantics(recipe) -> RecipeSemanticIndex`
  - `validate_provenance(recipe, index, companions) -> PhaseIssues`
  - `validate_clause_graph(recipe, index) -> PhaseIssues`
  - `validate_derived_facts(recipe, index, companions) -> PhaseIssues`

- [ ] **Step 1: Write stable-ID, projection, coverage, and derivation tests**

Use one valid neutral contract and assert these exact mutations:

| Mutation | Phase/code |
|---|---|
| nested postcondition duplicates parent `clause_id` | `clause_graph / duplicate_clause_id` |
| goal has no maintains or unresolved projection | `clause_graph / goal_projection_missing` |
| goal projects only to an invariant | `clause_graph / goal_projection_outcome_missing` |
| requirement supports no maintains/invariant | `clause_graph / orphan_requirement` |
| requirement cites the output it is meant to create as current evidence | `provenance / circular_requirement` |
| semantic artifact-value pointer is empty | `provenance / semantic_pointer_empty` |
| semantic artifact-value pointer uses URI-fragment form | `provenance / json_pointer_uri_fragment_forbidden` |
| semantic artifact-value pointer contains invalid `~2` escape | `provenance / json_pointer_escape_invalid` |
| maintained clause removes direct support and relies on a sibling | `provenance / material_clause_support_missing` |
| postcondition inherits from a non-parent maintains ID | `provenance / invalid_parent_support_inheritance` |
| canonicalization cites source support outside its parent’s declared support | `provenance / canonicalization_support_exceeds_parent` |
| multiply derives `10 * 10` as safe integer `100` | no issue; derived record is accepted |
| derivation operator becomes `add` | `derived_facts / unsupported_derivation_operator` |
| claimed derived value becomes `99` | `derived_facts / derived_value_mismatch` |

- [ ] **Step 2: Run semantic tests to establish the red state**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_semantics.py -q
```

Expected: import failure for `planner_graph_recipe_semantics`.

- [ ] **Step 3: Build one stable semantic index**

```python
@dataclass(frozen=True)
class RecipeSemanticIndex:
    clauses: Mapping[str, Mapping[str, Any]]
    clause_kinds: Mapping[str, str]
    parent_maintains: Mapping[str, str]
    assumptions: Mapping[str, Mapping[str, Any]]
    derived_facts: Mapping[str, Mapping[str, Any]]
    unresolved_intent: Mapping[str, Mapping[str, Any]]
    shape_entries: Mapping[str, Mapping[str, Any]]
    capabilities: Mapping[str, Mapping[str, Any]]
    worker_slots: Mapping[str, Mapping[str, Any]]
```

Index goal, requirements, maintains, nested canonicalization, nested postconditions, and invariants. Reject duplicate IDs before any sorting. Record only immediate parent-maintains inheritance for nested clauses.

- [ ] **Step 4: Implement closed provenance traversal**

For each prose-bearing material clause, resolve only:

- direct `source_refs`;
- direct `assumption_refs`;
- direct `derived_fact_refs`;
- requirements whose `supports_clause_ids` explicitly name it;
- immediate parent-maintains support for nested canonicalization/postcondition clauses declaring that exact parent.

Never borrow from goal, siblings, arbitrary ancestors, or general graph reachability. A clause with no references must carry its exact kind-specific synthesis code. Deterministic validation checks legal references and support structure; it must not claim prose entailment.

- [ ] **Step 5: Implement the v1 derived-fact allowlist**

Support only `multiply` over exactly two integer-valued authority/derived references for LM9A v1. Recompute with Python integers after safe-range validation; do not evaluate expressions or use `eval`. Validate the complete typed value and `typed_value_fingerprint`.

- [ ] **Step 6: Run focused tests and commit**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_semantics.py -q
git add mcp_server/src/rook/agent/planner_graph_recipe_semantics.py `
  mcp_server/tests/lm9a_contract_factory.py `
  mcp_server/tests/test_planner_graph_recipe_semantics.py
git commit -m "feat(lm9a): validate semantic clause graph"
```

Expected: all focused tests pass before commit.

---

### Task 6: Assumption Authorization, Confirmation Projection, And Unresolved Intent

**Files:**
- Modify: `mcp_server/src/rook/agent/planner_graph_recipe_semantics.py`
- Modify: `mcp_server/tests/test_planner_graph_recipe_semantics.py`
- Modify: `mcp_server/tests/lm9a_contract_factory.py`

**Interfaces:**
- Consumes: semantic index, companion policy/receipt authority, and trusted time/session.
- Produces:
  - `AssumptionAuthorization(assumption_id, status, policy_rule_ref, confirmation_receipt_ref)`
  - `confirmation_subject_projection(recipe, selected_assumption_ids) -> Mapping[str, Any]`
  - `confirmation_subject_fingerprint(recipe, selected_assumption_ids) -> str`
  - `validate_assumptions(recipe: Mapping[str, Any], index: RecipeSemanticIndex, companions: CompanionIndex) -> tuple[tuple[AssumptionAuthorization, ...], PhaseIssues]`
  - `validate_unresolved_intent(recipe: Mapping[str, Any], index: RecipeSemanticIndex, companions: CompanionIndex, authorizations: tuple[AssumptionAuthorization, ...]) -> PhaseIssues`

Extend `mcp_server/tests/lm9a_contract_factory.py` with these test-only helpers:

- `confirmable_contract_without_receipt() -> tuple[dict[str, Any], dict[str, Any]]`
- `attach_matching_confirmation_receipt(recipe, validation_input, subject_fingerprint) -> dict[str, Any]`
- `confirmed_contract() -> tuple[dict[str, Any], dict[str, Any]]`
- `apply_confirmation_mutation(recipe, validation_input, mutation_code) -> None`
- `semantic_diagnostic_codes(recipe, validation_input) -> set[str]`

- [ ] **Step 1: Write authorization matrix tests**

Use explicit policy mutations and assert:

| Case | Authorization/result |
|---|---|
| one exact allow rule covers key/type/unit/scope/value | `policy_auto`, no blocker |
| no applicable allow or prohibition | `confirmation_required`, blocker, `valid=true` |
| one applicable prohibition | `policy_prohibited`, blocker, `valid=true` |
| two applicable rules | `policy_ambiguous`, blocker, `valid=true` |
| exact default exists while an unresolved entry claims absence | invalid `stale_unresolved_intent` |
| unit-context fingerprint differs | `confirmation_required`, not silent authorization |
| typed material value has no fact/derivation/assumption authority | error `material_value_authority_missing` |
| assumption’s typed value conflicts with a directly cited same-key authoritative typed value | error `assumption_authority_value_conflict` |

Use `Decimal` for all scalar equality/range checks. Assert that `"2"`, `"2.0"`, and `"2.00"` compare equal but have distinct typed-value fingerprints.

Do not parse unrestricted prose to manufacture a disagreement result. LM9A may
report `statement_typed_value_mismatch` only when the contradiction is exposed
by closed structured backing; ordinary prose fidelity remains outside
deterministic validation.

- [ ] **Step 2: Write confirmation subject and receipt tests**

```python
def test_attaching_selected_receipt_keeps_subject_fingerprint_stable():
    before, context = confirmable_contract_without_receipt()
    subject = confirmation_subject_fingerprint(before, ("assumption.some_value",))
    after = attach_matching_confirmation_receipt(before, context, subject)
    assert confirmation_subject_fingerprint(
        after, ("assumption.some_value",)
    ) == subject
    assert after["recipe_fingerprint"] != before["recipe_fingerprint"]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("remove_selected_descriptor", "confirmation_receipt_missing"),
        ("duplicate_selected_descriptor", "confirmation_receipt_duplicate"),
        ("bind_other_assumption", "confirmation_assumption_mismatch"),
        ("reuse_receipt", "confirmation_receipt_shared"),
        ("expire_receipt", "confirmation_receipt_expired"),
        ("change_task_session", "confirmation_task_session_mismatch"),
        ("set_rejected", "confirmation_not_confirmed"),
    ],
)
def test_confirmation_receipt_failures_are_exact(mutation, expected_code):
    recipe, context = confirmed_contract()
    apply_confirmation_mutation(recipe, context, mutation)
    assert expected_code in semantic_diagnostic_codes(recipe, context)
```

Add separate positive assertions that only the selected descriptor is removed,
semantic/policy changes move the subject, and a non-null confirmation reference
on `policy_auto` produces `gratuitous_confirmation_ref`.

- [ ] **Step 3: Implement derived authorization and exact subject projection**

Authorization is validator-derived; never trust an `authorization.mode` from recipe prose. Closed statuses are:

```text
policy_auto
confirmation_required
confirmed
trusted_selection_required
privileged_authorization_required
policy_prohibited
policy_ambiguous
```

For the confirmation subject:

1. Deep-copy the normalized recipe.
2. Remove `recipe_fingerprint`.
3. Select exactly assumptions whose derived outcome is `confirmation_required` or `confirmed`.
4. Replace each selected assumption’s required `confirmation_ref` value with explicit `null`.
5. Remove only authority-artifact descriptors that resolve to the selected assumptions’ exact confirmation receipts.
6. Leave every unselected authority descriptor and semantic field intact.
7. Canonicalize and hash.

The ordinary recipe fingerprint still includes the attached receipt descriptor and reference.

- [ ] **Step 4: Implement unresolved-intent honesty**

Validate unique `semantic_key`, legal affected clause IDs reachable from goal projection, registered future value schema, permitted authority/outcome lists, and absence of an already supplied matching authority value. Enforce:

```text
unresolved entry present -> valid may remain true, compile blocker emitted
same key in assumption and unresolved -> invalid
exact policy default already supplies value -> unresolved entry invalid
policy range only -> unresolved remains honest
confirmation-required assumption -> not unresolved
```

No compiler/worker/executable artifact may be created for unresolved recipes.

- [ ] **Step 5: Run semantic tests and commit**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_semantics.py -q
git add mcp_server/src/rook/agent/planner_graph_recipe_semantics.py `
  mcp_server/tests/lm9a_contract_factory.py `
  mcp_server/tests/test_planner_graph_recipe_semantics.py
git commit -m "feat(lm9a): validate assumptions and unresolved intent"
```

Expected: all focused tests pass.

---

### Task 7: Shape, Capability, Worker-Slot, And Readiness Validation

**Files:**
- Modify: `mcp_server/src/rook/agent/planner_graph_recipe_semantics.py`
- Modify: `mcp_server/tests/test_planner_graph_recipe_semantics.py`

**Interfaces:**
- Consumes: semantic index plus validated authority/capability/slot vocabularies and capability registry.
- Produces:
  - `validate_shape(recipe: Mapping[str, Any], index: RecipeSemanticIndex, companions: CompanionIndex) -> PhaseIssues`
  - `validate_capabilities(recipe: Mapping[str, Any], index: RecipeSemanticIndex, companions: CompanionIndex) -> PhaseIssues`
  - `validate_worker_slots(recipe: Mapping[str, Any], index: RecipeSemanticIndex, companions: CompanionIndex) -> PhaseIssues`
  - `validate_readiness(phase_rows: tuple[Mapping[str, Any], ...], authorizations: tuple[AssumptionAuthorization, ...]) -> PhaseIssues`

- [ ] **Step 1: Write shape/capability/slot tests**

Use this exact case matrix:

| Mutation/assertion | Phase/code |
|---|---|
| `select_representation` absent from `delegates` | no error; exported delegation allowlist excludes that code |
| same authority code in `self` and `delegates` | `shape / retained_delegated_overlap` |
| same entry in `delegates` and `prohibited` | `shape / delegated_prohibited_overlap` |
| unknown authority code or delegate kind | `shape / unknown_authority_code` or `invalid_delegate_kind` |
| capability supports a disallowed clause kind | `capabilities / capability_clause_kind_invalid` |
| available capability has empty implementation refs | `companion_artifacts / available_capability_implementation_missing` |
| required capability is unavailable | `capabilities / capability_unavailable` blocker |
| slot/delegate link missing in either direction | `worker_slots / worker_slot_link_mismatch` |
| output schema or input kind outside slot vocabulary | `worker_slots / worker_slot_schema_not_allowed` or `worker_slot_input_kind_not_allowed` |
| slot has empty maintained support | `worker_slots / worker_slot_support_missing` |
| `worker_slots.entries` is empty | valid and no request/output/provider/model artifact exists |

- [ ] **Step 2: Implement shape validation**

Treat `delegates` as a closed allowlist. Unknown codes are errors; a code in `self` and `delegates`, or `delegates` and `prohibited`, is invalid. Validate every statement against its closed code only for deterministic contradictions; do not infer broader authority from prose. Representation authority never grants execution or mutation authority.

- [ ] **Step 3: Implement capability validation**

Require each capability entry to name a known generic vocabulary code and legal supporting clause kinds. Resolve trusted availability from the environment registry. `required_capabilities` expresses semantic need only: available implementations do not grant authority, and unavailable capability evidence emits a blocker rather than changing recipe meaning. Result observation is not a v1 recipe capability and no observation support dependency is emitted by LM9A; that remains a mandatory future compile-output rule.

- [ ] **Step 4: Implement exact shape-to-worker-slot linkage**

For every worker slot, require exactly one `instantiate_worker_slot` delegate whose `worker_slot_id` points back to it, and require the slot’s `permitted_under_shape_id` to point to that delegate. Check output-schema allowlist, input-reference kind allowlist, declared inputs, and nonempty existing maintains support. `worker_slots.entries: []` produces no request and grants no worker authority.

- [ ] **Step 5: Implement readiness blockers**

Readiness aggregates evaluated phase outcomes without running compilation. A valid recipe is compile-ready only when no blockers remain. Trusted target selection and privileged authority remain deferred v1 blockers; any supplied reserved receipt kind remains invalid. Capability unavailability, unresolved intent, pending confirmation, prohibition, and ambiguity remain exact blockers.

- [ ] **Step 6: Run semantic tests and commit**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_semantics.py -q
git add mcp_server/src/rook/agent/planner_graph_recipe_semantics.py `
  mcp_server/tests/test_planner_graph_recipe_semantics.py
git commit -m "feat(lm9a): validate semantic delegation readiness"
```

Expected: all focused tests pass.

---

### Task 8: Public Validator Orchestration And Closed Report Fingerprints

**Files:**
- Create: `mcp_server/src/rook/agent/planner_graph_recipe_rules.py`
- Create: `mcp_server/src/rook/agent/planner_graph_recipe_validate.py`
- Create: `mcp_server/tests/test_planner_graph_recipe_rules.py`
- Create: `mcp_server/tests/test_planner_graph_recipe_validate.py`
- Modify: `mcp_server/tests/lm9a_contract_factory.py`

**Interfaces:**
- Consumes: candidate recipe bytes and candidate validation input at the public
  boundary; phase validation consumes only the exact bytes, validator identity,
  trusted context, and immutable validation-input snapshot established by
  invocation preflight.
- Produces:
  - `RULESET_MANIFEST`
  - `RULESET_MODULES`
  - `ruleset_projection(manifest, source_bytes_by_module) -> Mapping[str, Any]`
  - `compute_ruleset_fingerprint(manifest=RULESET_MANIFEST, source_bytes_by_module=None) -> str`
  - `assert_registered_issue(phase: str, code: str, issue_kind: str, severity: str | None = None) -> None`
  - `REPORT_CONSTRUCTABILITY_SHELLS`
  - `ValidationInvocationContext(raw_recipe_bytes, input_payload_sha256, validation_input_snapshot, trusted_validation_context, validator_identity)`
  - `ValidationInvocationFailure(kind, failure_stage, code, input_payload_sha256, validation_input_snapshot_fingerprint, subject_path, message)`
  - `resolve_validator_identity() -> Mapping[str, str]`
  - `preflight_validation_invocation(raw_recipe_bytes: object, validation_input: object) -> ValidationInvocationContext | ValidationInvocationFailure`
  - `validate_preflighted(context: ValidationInvocationContext) -> Mapping[str, Any] | ValidationInvocationFailure`
  - `PHASE_RUNNERS`
  - `validate_planner_graph_recipe(raw_recipe_bytes: object, validation_input: object) -> Mapping[str, Any] | ValidationInvocationFailure`
  - no other artifacts or side effects.

Extend `mcp_server/tests/lm9a_contract_factory.py` with:

- `recompute_report_fingerprint(report: Mapping[str, Any]) -> str`
- `recompute_validation_context_fingerprint(report: Mapping[str, Any]) -> str`
- `phase(report: Mapping[str, Any], phase_name: str) -> str`
- `blocker_codes(report: Mapping[str, Any]) -> set[str]`

- [ ] **Step 1: Write ruleset-manifest identity tests**

```python
def test_ruleset_manifest_covers_every_phase_and_stable_issue_code():
    assert RULESET_MANIFEST["runtime_dependencies"] == {
        "jsonschema": "4.26.0",
        "jsonschema-specifications": "2025.9.1",
        "referencing": "0.37.0",
    }
    assert tuple(entry["phase"] for entry in RULESET_MANIFEST["phases"]) == PHASE_ORDER
    for entry in RULESET_MANIFEST["phases"]:
        assert entry["algorithm_version"].startswith("lm9a.")
        assert tuple(entry["diagnostic_codes"]) == (
            RULESET_PHASE_CODES[entry["phase"]]["diagnostic_codes"]
        )
        assert tuple(entry["blocker_codes"]) == (
            RULESET_PHASE_CODES[entry["phase"]]["blocker_codes"]
        )
        assert set(entry) == {
            "phase",
            "algorithm_version",
            "implementation_modules",
            "diagnostic_codes",
            "blocker_codes",
        }


def test_ruleset_runtime_dependency_versions_match_installed_distributions():
    for distribution, expected in RULESET_MANIFEST["runtime_dependencies"].items():
        assert importlib.metadata.version(distribution) == expected


def test_ruleset_fingerprint_moves_with_manifest_rule_change():
    sources = fixed_ruleset_sources()
    changed = copy.deepcopy(RULESET_MANIFEST)
    changed["phases"][0]["algorithm_version"] = "lm9a.schema:v2"
    assert compute_ruleset_fingerprint(source_bytes_by_module=sources) != (
        compute_ruleset_fingerprint(changed, sources)
    )


def test_ruleset_fingerprint_moves_with_metaschema_dependency_change():
    sources = fixed_ruleset_sources()
    changed = copy.deepcopy(RULESET_MANIFEST)
    changed["runtime_dependencies"]["jsonschema-specifications"] = "2025.9.2"
    assert compute_ruleset_fingerprint(source_bytes_by_module=sources) != (
        compute_ruleset_fingerprint(changed, sources)
    )


def test_ruleset_fingerprint_moves_with_production_rule_source_change():
    sources = fixed_ruleset_sources()
    changed = dict(sources)
    changed["rook.agent.planner_graph_recipe_semantics"] += b"\n# behavior revision\n"
    assert compute_ruleset_fingerprint(source_bytes_by_module=sources) != (
        compute_ruleset_fingerprint(source_bytes_by_module=changed)
    )


def test_source_hash_normalizes_crlf_to_lf():
    lf = fixed_ruleset_sources()
    crlf = {name: raw.replace(b"\n", b"\r\n") for name, raw in lf.items()}
    assert compute_ruleset_fingerprint(source_bytes_by_module=lf) == (
        compute_ruleset_fingerprint(source_bytes_by_module=crlf)
    )


def test_unregistered_issue_code_is_rejected_before_report_emission():
    with pytest.raises(RulesetIdentityError, match="ruleset_issue_code_unregistered"):
        assert_registered_issue("assumptions", "invented_code", "diagnostic")


def test_registered_code_under_wrong_classification_is_rejected():
    with pytest.raises(
        RulesetIdentityError,
        match="ruleset_issue_classification_mismatch",
    ):
        assert_registered_issue(
            "assumptions",
            "material_value_authority_missing",
            "blocker",
        )


def test_registered_diagnostic_with_wrong_severity_is_rejected():
    with pytest.raises(RulesetIdentityError, match="ruleset_issue_severity_mismatch"):
        assert_registered_issue(
            "assumptions",
            "material_value_authority_missing",
            "diagnostic",
            severity="warning",
        )
```

- [ ] **Step 2: Run ruleset tests to establish the red state**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_rules.py -q
```

Expected: import failure for `planner_graph_recipe_rules`.

- [ ] **Step 3: Implement the versioned ruleset manifest and source projection**

`RULESET_MANIFEST` is a closed object with schema
`rook.planner_graph_recipe_validator_ruleset:v1`, implementation version,
canonicalization version, exact product-schema fingerprints, the fixed phase
graph, the exhaustive set-order table fingerprint, required vocabulary
fingerprints, exact runtime dependency versions for `jsonschema`,
`jsonschema-specifications`, and `referencing`, and one phase row for every
`PHASE_ORDER` entry. `resolve_validator_identity()` checks those versions against
`importlib.metadata.version(...)` and computes the complete ruleset fingerprint
during invocation preflight, before any report is attempted. A dependency,
source, or ruleset-identity mismatch returns
`validator_identity_unavailable`; it must not escape during module import or
emit a report under a false fingerprint. The manifest contains
this exact exhaustive v1 phase/code registry; no other report issue code is
permitted:

```python
RULESET_PHASE_CODES = {
    "schema": {
        "diagnostic_codes": (
            "utf8_bom_forbidden",
            "invalid_utf8",
            "invalid_json",
            "duplicate_object_member",
            "nonfinite_json_number",
            "json_number_token_too_long",
            "invalid_json_number",
            "unpaired_unicode_surrogate",
            "recipe_input_bytes_exceeded",
            "recipe_json_depth_exceeded",
            "schema_validation_failed",
            "non_integer_product_number",
            "unsafe_json_integer",
            "semantic_prose_outer_whitespace",
        ),
        "blocker_codes": (),
    },
    "fingerprint": {
        "diagnostic_codes": ("recipe_fingerprint_mismatch",),
        "blocker_codes": (),
    },
    "companion_artifacts": {
        "diagnostic_codes": (
            "validation_input_schema_failed",
            "companion_schema_validation_failed",
            "companion_artifact_id_duplicate",
            "recipe_authority_companion_missing",
            "recipe_authority_companion_extra",
            "companion_kind_mismatch",
            "companion_schema_mismatch",
            "companion_fingerprint_mismatch",
            "companion_fingerprint_uncomputable",
            "recipe_companion_fingerprint_mismatch",
            "environment_snapshot_expired",
            "environment_session_mismatch",
            "planning_policy_expired",
            "capability_registry_expired",
            "capability_registry_session_mismatch",
            "payload_schema_registry_entry_missing",
            "payload_schema_registry_entry_duplicate",
            "payload_schema_fingerprint_mismatch",
            "payload_schema_dialect_mismatch",
            "payload_schema_invalid",
            "payload_schema_remote_ref",
            "payload_schema_dynamic_ref_forbidden",
            "payload_schema_recursive_ref_forbidden",
            "payload_schema_identifier_forbidden",
            "payload_schema_anchor_forbidden",
            "payload_schema_dynamic_anchor_forbidden",
            "payload_schema_reference_unresolvable",
            "payload_validation_failed",
            "value_binding_id_duplicate",
            "duplicate_value_binding_pointer",
            "value_binding_pointer_invalid",
            "value_binding_pointer_unresolved",
            "semantic_value_schema_unknown",
            "bound_value_schema_invalid",
            "typed_value_fingerprint_mismatch",
            "policy_rule_key_mismatch",
            "policy_rule_overlap",
            "capability_registry_entry_duplicate",
            "available_capability_implementation_missing",
            "unavailable_capability_implementation_present",
            "vocabulary_missing",
            "vocabulary_duplicate",
            "vocabulary_version_mismatch",
            "vocabulary_required_entry_missing",
            "vocabulary_unknown_entry",
            "vocabulary_fingerprint_mismatch",
            "deferred_receipt_kind",
        ),
        "blocker_codes": (),
    },
    "provenance": {
        "diagnostic_codes": (
            "semantic_pointer_empty",
            "json_pointer_uri_fragment_forbidden",
            "json_pointer_escape_invalid",
            "json_pointer_index_invalid",
            "semantic_reference_artifact_unknown",
            "semantic_reference_binding_missing",
            "source_reference_dangling",
            "assumption_reference_dangling",
            "derived_fact_reference_dangling",
            "requirement_support_reference_dangling",
            "material_clause_support_missing",
            "planner_synthesis_missing",
            "invalid_parent_support_inheritance",
            "canonicalization_support_exceeds_parent",
            "circular_requirement",
        ),
        "blocker_codes": (),
    },
    "clause_graph": {
        "diagnostic_codes": (
            "duplicate_clause_id",
            "goal_projection_missing",
            "goal_projection_outcome_missing",
            "goal_projection_reference_dangling",
            "orphan_requirement",
        ),
        "blocker_codes": (),
    },
    "derived_facts": {
        "diagnostic_codes": (
            "duplicate_derived_fact_id",
            "unsupported_derivation_operator",
            "derived_input_count_invalid",
            "derived_input_reference_invalid",
            "derived_input_type_invalid",
            "derived_value_unsafe_integer",
            "derived_value_mismatch",
            "derived_typed_value_fingerprint_mismatch",
        ),
        "blocker_codes": (),
    },
    "assumptions": {
        "diagnostic_codes": (
            "duplicate_assumption_id",
            "material_value_authority_missing",
            "assumption_authority_value_conflict",
            "statement_typed_value_mismatch",
            "assumption_basis_reference_invalid",
            "assumption_policy_reference_invalid",
            "confirmation_receipt_missing",
            "confirmation_receipt_duplicate",
            "confirmation_assumption_mismatch",
            "confirmation_receipt_shared",
            "confirmation_receipt_expired",
            "confirmation_task_session_mismatch",
            "confirmation_not_confirmed",
            "confirmation_task_fingerprint_mismatch",
            "confirmation_subject_fingerprint_mismatch",
            "confirmation_typed_value_fingerprint_mismatch",
            "confirmation_receipt_reference_mismatch",
            "gratuitous_confirmation_ref",
        ),
        "blocker_codes": (
            "confirmation_required",
            "trusted_selection_required",
            "privileged_authorization_required",
            "policy_prohibited",
            "policy_ambiguous",
        ),
    },
    "unresolved_intent": {
        "diagnostic_codes": (
            "duplicate_unresolved_intent_id",
            "duplicate_unresolved_semantic_key",
            "stale_unresolved_intent",
            "unresolved_assumption_conflict",
            "unresolved_affected_clause_invalid",
            "unresolved_goal_projection_unreachable",
            "unresolved_value_schema_unknown",
            "unresolved_unit_context_invalid",
        ),
        "blocker_codes": ("unresolved_intent",),
    },
    "shape": {
        "diagnostic_codes": (
            "duplicate_shape_id",
            "retained_delegated_overlap",
            "delegated_prohibited_overlap",
            "unknown_authority_code",
            "invalid_delegate_kind",
            "shape_section_not_allowed",
            "shape_statement_code_conflict",
        ),
        "blocker_codes": (),
    },
    "capabilities": {
        "diagnostic_codes": (
            "duplicate_capability_id",
            "unknown_capability_code",
            "capability_clause_kind_invalid",
            "capability_support_missing",
            "capability_support_reference_invalid",
            "capability_registry_entry_missing",
        ),
        "blocker_codes": ("capability_unavailable",),
    },
    "worker_slots": {
        "diagnostic_codes": (
            "duplicate_worker_slot_id",
            "unknown_worker_slot_code",
            "worker_slot_link_mismatch",
            "worker_slot_delegate_duplicate",
            "worker_slot_schema_not_allowed",
            "worker_slot_input_kind_not_allowed",
            "worker_slot_input_reference_invalid",
            "worker_slot_support_missing",
            "worker_slot_support_reference_invalid",
        ),
        "blocker_codes": (),
    },
    "readiness": {
        "diagnostic_codes": (),
        "blocker_codes": (),
    },
}
```

All v1 diagnostics above have severity `error`; LM9A v1 emits no production
warning or information code. Internal `jsonschema` validator keyword names are
not public report codes: recipe/validation-input schema failures normalize to
`schema_validation_failed`, while registered payload-schema boundary failures
normalize to their exact `companion_artifacts` codes above.

The `validation_input_snapshot_*`, `report_constructability_*`, and trusted
context codes are pre-report `ValidationInvocationFailure` codes, not phase
diagnostics. They therefore do not appear in `RULESET_PHASE_CODES` or the
145-row report issue registry. Their behavior remains bound by the closed spec,
the validator source projection, and public preflight tests.

`RULESET_MANIFEST["phases"]` copies these exact tuples into phase rows alongside
the phase algorithm version and implementation modules. Manifest self-validation
rejects a missing phase, an extra phase, duplicate codes, a code listed
under both classifications for one phase, or any drift from
`RULESET_PHASE_CODES`.

`RULESET_MODULES` contains exactly these production modules:

```python
RULESET_MODULES = (
    "rook.agent.planner_graph_recipe_canonical",
    "rook.agent.planner_graph_recipe_schemas",
    "rook.agent.planner_graph_recipe_report",
    "rook.agent.planner_graph_recipe_authority",
    "rook.agent.planner_graph_recipe_semantics",
    "rook.agent.planner_graph_recipe_rules",
    "rook.agent.planner_graph_recipe_validate",
)
```

For each module, resolve and read its UTF-8 source without importing it, reject
a BOM or unavailable/non-`.py` source, normalize CRLF/CR to LF, and record:

```yaml
module: rook.agent.planner_graph_recipe_semantics
source_sha256: sha256:...
```

Resolve each source path with `importlib.util.find_spec(module_name).origin` and
read the `.py` file directly. Do not import the modules merely to discover
their source paths; ruleset identity computation must not execute production
module top-level code or create a `rules -> validate -> rules` import cycle.

The canonical ruleset projection contains the complete normalized manifest and
the source rows sorted by module name. `compute_ruleset_fingerprint` returns
`canonical_sha256(projection)`. If any source cannot be bound, raise
`RulesetIdentityError("ruleset_source_unavailable")`; do not emit a conforming
validation report with a partial ruleset identity.

- [ ] **Step 4: Write end-to-end report tests**

```python
def test_valid_report_recomputes_recipe_context_and_report_fingerprints():
    recipe, validation_input = minimal_valid_contract()
    report = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert report["valid"] is True
    assert report["compile_ready"] is True
    assert report["validation_input_snapshot_fingerprint"] == (
        snapshot_json_tree(validation_input).fingerprint
    )
    assert report["claimed_recipe_fingerprint"] == report["computed_recipe_fingerprint"]
    assert report["validation_context"]["validation_context_fingerprint"] == (
        recompute_validation_context_fingerprint(report)
    )
    assert report["report_fingerprint"] == recompute_report_fingerprint(report)
    assert validate_closed_payload(
        report, "rook.planner_graph_recipe_validation_report:v1"
    ) == ()


def test_validation_context_fingerprint_tampering_is_independently_detectable():
    recipe, validation_input = minimal_valid_contract()
    report = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    tampered = copy.deepcopy(report)
    tampered["validation_context"]["validation_context_fingerprint"] = (
        "sha256:" + ("0" * 64)
    )
    assert tampered["validation_context"]["validation_context_fingerprint"] != (
        recompute_validation_context_fingerprint(tampered)
    )


def test_malformed_raw_input_retains_raw_hash_and_null_computed_fingerprint():
    _, validation_input = minimal_valid_contract()
    report = validate_planner_graph_recipe(b'{"schema":', validation_input)
    assert report["input_payload_sha256"].startswith("sha256:")
    assert report["computed_recipe_fingerprint"] is None
    assert report["valid"] is False
    assert phase(report, "schema") == "failed"


@pytest.mark.parametrize(
    ("raw_recipe_bytes", "input_mutation", "expected_code", "has_hash"),
    [
        (None, None, "raw_recipe_bytes_unavailable", False),
        (b"{}", "remove_input", "validation_input_unavailable", True),
        (b"{}", "remove_context", "report_constructability_envelope_missing", True),
        (b"{}", "remove_trusted_field", "trusted_validation_context_missing", True),
        (b"{}", "invalidate_context", "trusted_validation_context_invalid", True),
    ],
)
def test_pre_report_invocation_failures_do_not_masquerade_as_reports(
    raw_recipe_bytes,
    input_mutation,
    expected_code,
    has_hash,
):
    _, validation_input = minimal_valid_contract()
    if input_mutation == "remove_input":
        validation_input = None
    elif input_mutation == "remove_context":
        del validation_input["validation_context"]
    elif input_mutation == "remove_trusted_field":
        del validation_input["validation_context"]["evaluated_at"]
    elif input_mutation == "invalidate_context":
        validation_input["validation_context"]["evaluated_at"] = "not-a-timestamp"

    result = validate_planner_graph_recipe(raw_recipe_bytes, validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.kind == "invocation_failure"
    assert result.failure_stage == "preflight"
    assert result.code == expected_code
    assert (result.input_payload_sha256 is not None) is has_hash
    assert len(result.message) <= MAX_EVIDENCE_MESSAGE_CHARS
    assert not hasattr(result, "valid")


def mutate_pointer(document, pointer, *, delete=False, value=None):
    parts = pointer.lstrip("/").split("/")
    parent = document
    for part in parts[:-1]:
        parent = parent[part]
    if delete:
        del parent[parts[-1]]
    else:
        parent[parts[-1]] = value


@pytest.mark.parametrize(
    ("path", "wrong_type", "expected_code"),
    [
        ("/task_envelope", None, "report_constructability_envelope_missing"),
        ("/authority_artifacts", {}, "report_constructability_envelope_invalid"),
        (
            "/validation_context/payload_schema_registry",
            None,
            "report_constructability_envelope_missing",
        ),
        (
            "/validation_context/vocabularies/worker_slot_codes",
            [],
            "report_constructability_envelope_invalid",
        ),
    ],
)
def test_report_constructability_shells_fail_before_report(
    path,
    wrong_type,
    expected_code,
):
    _, validation_input = minimal_valid_contract()
    mutate_pointer(validation_input, path, delete=wrong_type is None, value=wrong_type)
    result = validate_planner_graph_recipe(b'{"schema":', validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.code == expected_code
    assert result.subject_path == path
    assert result.validation_input_snapshot_fingerprint.startswith("sha256:")


@pytest.mark.parametrize(
    ("value", "expected_code"),
    [
        (float("inf"), "validation_input_snapshot_nonfinite_number"),
        (10**400, "validation_input_snapshot_integer_out_of_jcs_domain"),
        (Decimal("1"), "validation_input_snapshot_non_json_host_type"),
        (b"x", "validation_input_snapshot_non_json_host_type"),
        ((1, 2), "validation_input_snapshot_non_json_host_type"),
    ],
)
def test_snapshot_host_value_failures_are_pre_report(value, expected_code):
    _, validation_input = minimal_valid_contract()
    validation_input["validation_context"]["payload_schema_registry"]["hostile"] = value
    result = validate_planner_graph_recipe(b"{}", validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.code == expected_code
    assert result.validation_input_snapshot_fingerprint is None


def test_snapshot_depth_and_cycle_fail_at_public_preflight():
    _, too_deep = minimal_valid_contract()
    value = 0
    for _ in range(64):
        value = [value]
    too_deep["validation_context"]["payload_schema_registry"]["hostile"] = value
    result = validate_planner_graph_recipe(b"{}", too_deep)
    assert result.code == "validation_input_snapshot_depth_exceeded"

    _, cyclic = minimal_valid_contract()
    cycle = []
    cycle.append(cycle)
    cyclic["validation_context"]["payload_schema_registry"]["hostile"] = cycle
    result = validate_planner_graph_recipe(b"{}", cyclic)
    assert result.code == "validation_input_snapshot_repeated_container"


def test_original_mapping_mutation_after_preflight_cannot_change_report():
    recipe, original = minimal_valid_contract()
    context = preflight_validation_invocation(raw_recipe_bytes(recipe), original)
    assert isinstance(context, ValidationInvocationContext)
    frozen_fingerprint = context.validation_input_snapshot.fingerprint

    original["task_envelope"]["task_session_id"] = "session.mutated"
    original["validation_context"]["evaluated_at"] = "2099-01-01T00:00:00Z"

    report = validate_preflighted(context)
    assert report["validation_input_snapshot_fingerprint"] == frozen_fingerprint
    assert report["source_task"]["task_session_id"] != "session.mutated"
    assert report["validation_context"]["evaluated_at"] != "2099-01-01T00:00:00Z"


def test_each_phase_receives_a_fresh_thaw_of_the_snapshot(monkeypatch):
    recipe, validation_input = minimal_valid_contract()
    seen = []

    def mutating_runner(*, validation_input, **_):
        validation_input["task_envelope"]["artifact_id"] = "mutated"
        return PhaseIssues()

    def observing_runner(*, validation_input, **_):
        seen.append(validation_input["task_envelope"]["artifact_id"])
        return PhaseIssues()

    monkeypatch.setitem(PHASE_RUNNERS, "provenance", mutating_runner)
    monkeypatch.setitem(PHASE_RUNNERS, "clause_graph", observing_runner)
    validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert seen == ["task_envelope"]


def test_ruleset_identity_failure_is_a_pre_report_invocation_failure(monkeypatch):
    recipe, validation_input = minimal_valid_contract()
    monkeypatch.setattr(
        validate_module,
        "resolve_validator_identity",
        lambda: (_ for _ in ()).throw(
            RulesetIdentityError("ruleset_source_unavailable")
        ),
    )
    result = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.failure_stage == "preflight"
    assert result.code == "validator_identity_unavailable"
    assert result.input_payload_sha256.startswith("sha256:")


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        (
            b"0" + (b" " * MAX_RECIPE_INPUT_BYTES),
            "recipe_input_bytes_exceeded",
        ),
        (
            (b"[" * 65) + b"0" + (b"]" * 65),
            "recipe_json_depth_exceeded",
        ),
        (
            (b"[" * 2_000) + b"0" + (b"]" * 2_000),
            "recipe_json_depth_exceeded",
        ),
        (b'{"value":1e10000}', "nonfinite_json_number"),
        (
            b'{"value":' + (b"9" * 5_000) + b"}",
            "json_number_token_too_long",
        ),
    ],
)
def test_raw_resource_limits_always_emit_schema_phase_report(raw, expected_code):
    _, validation_input = minimal_valid_contract()
    report = validate_planner_graph_recipe(raw, validation_input)
    assert report["input_payload_sha256"].startswith("sha256:")
    assert report["computed_recipe_fingerprint"] is None
    assert phase(report, "schema") == "failed"
    assert diagnostic_codes(report) == {expected_code}


def test_validation_input_envelope_failure_with_trusted_context_is_reportable():
    recipe, validation_input = minimal_valid_contract()
    validation_input["unknown"] = True
    report = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert phase(report, "schema") == "passed"
    assert phase(report, "companion_artifacts") == "failed"
    assert diagnostic_codes(report) == {"validation_input_schema_failed"}


def test_nested_companion_schema_failure_belongs_to_companion_phase():
    recipe, validation_input = minimal_valid_contract()
    validation_input["task_envelope"]["unknown"] = True
    report = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert phase(report, "schema") == "passed"
    assert phase(report, "companion_artifacts") == "failed"
    assert diagnostic_codes(report) == {"companion_schema_validation_failed"}


def test_malformed_recipe_still_evaluates_valid_companion_snapshot():
    _, validation_input = minimal_valid_contract()
    report = validate_planner_graph_recipe(b'{"schema":', validation_input)
    assert phase(report, "schema") == "failed"
    assert phase(report, "companion_artifacts") == "passed"
    assert phase(report, "clause_graph") == "not_evaluated"


def test_malformed_recipe_and_malformed_companion_are_both_receipted():
    _, validation_input = minimal_valid_contract()
    validation_input["task_envelope"]["unknown"] = True
    report = validate_planner_graph_recipe(b'{"schema":', validation_input)
    assert phase(report, "schema") == "failed"
    assert phase(report, "companion_artifacts") == "failed"
    assert diagnostic_codes(report) == {
        "invalid_json",
        "companion_schema_validation_failed",
    }
    assert report["source_task"]["validation_status"] == "failed"
    assert report["validation_input_snapshot_fingerprint"].startswith("sha256:")


def test_orchestrator_receipts_unregistered_phase_issue_before_ledger_insert(monkeypatch):
    recipe, validation_input = minimal_valid_contract()
    monkeypatch.setitem(
        PHASE_RUNNERS,
        "assumptions",
        lambda **_: PhaseIssues(
            diagnostics=(diagnostic("assumptions", "invented_code"),)
        ),
    )
    result = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.failure_stage == "validation"
    assert result.code == "validator_integrity_failure"


def test_orchestrator_receipts_wrong_severity_before_ledger_insert(monkeypatch):
    recipe, validation_input = minimal_valid_contract()
    monkeypatch.setitem(
        PHASE_RUNNERS,
        "assumptions",
        lambda **_: PhaseIssues(
            diagnostics=(
                diagnostic(
                    "assumptions",
                    "material_value_authority_missing",
                    severity="warning",
                ),
            )
        ),
    )
    result = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.failure_stage == "validation"
    assert result.code == "validator_integrity_failure"


def test_orchestrator_receipts_wrong_issue_classification_before_ledger_insert(
    monkeypatch,
):
    recipe, validation_input = minimal_valid_contract()
    monkeypatch.setitem(
        PHASE_RUNNERS,
        "assumptions",
        lambda **_: PhaseIssues(
            blockers=(blocker("assumptions", "material_value_authority_missing"),)
        ),
    )
    result = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.failure_stage == "validation"
    assert result.code == "validator_integrity_failure"


def test_orchestrator_receipts_unexpected_implementation_failure(monkeypatch):
    recipe, validation_input = minimal_valid_contract()
    monkeypatch.setitem(
        PHASE_RUNNERS,
        "assumptions",
        lambda **_: (_ for _ in ()).throw(RuntimeError("secret detail")),
    )
    result = validate_planner_graph_recipe(raw_recipe_bytes(recipe), validation_input)
    assert isinstance(result, ValidationInvocationFailure)
    assert result.failure_stage == "validation"
    assert result.code == "validator_internal_failure"
    assert "secret detail" not in result.message


```

Parameterize the context branches above over a missing trusted field, a
malformed/non-UTC `evaluated_at`, an unknown clock source, malformed
task/capability session IDs, and a malformed non-null environment session ID.
A missing trusted field returns
`preflight / trusted_validation_context_missing`; a malformed field returns
`preflight / trusted_validation_context_invalid`. Absence or non-mapping type of
the `validation_context` shell is instead the earlier
`report_constructability_envelope_missing` or
`report_constructability_envelope_invalid` failure.

Add these explicit report assertions:

| Setup | Required report result |
|---|---|
| wrong claimed recipe fingerprint plus dangling goal projection | `fingerprint` and `clause_graph` both fail |
| malformed task envelope | `companion_artifacts=failed / companion_schema_validation_failed`; provenance and dependent phases `not_evaluated` |
| malformed recipe plus valid companion shells | `schema=failed`; `companion_artifacts=passed`; semantic phases requiring schema are `not_evaluated` |
| malformed recipe plus malformed task contents inside a present shell | `schema=failed` and `companion_artifacts=failed` in one conforming report |
| malformed recipe plus missing mandatory shell | preflight invocation failure; no report |
| confirmation blocker plus otherwise evaluable unresolved phase | `assumptions=blocked`; `unresolved_intent` evaluated |
| every public v1 report | no warning/information diagnostics; Task 3 ledger tests separately prove their status semantics |
| attempt to add identical issue as blocker and diagnostic | internal ledger raises `issue_classification_conflict`; public boundary returns `validation / validator_integrity_failure` before report emission |
| every valid/blocked report | top-level keys contain no compiler, worker request/output, executable, tool, or runtime receipt field |

Separately, unavailable validator identity, missing recipe bytes, missing
validation input, missing/malformed trusted validation context, validator
integrity assertions, and implementation exceptions before report completion
return a `ValidationInvocationFailure`, not any row in this report table.

- [ ] **Step 5: Run validator tests to establish the red state**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_validate.py -q
```

Expected: import failure for `planner_graph_recipe_validate`.

- [ ] **Step 6: Implement fixed phase orchestration**

Implement invocation preflight before parsing or phase construction. Its checks
run in this exact order:

```text
1. resolve exact validator/ruleset/canonicalization/runtime identity
2. require raw_recipe_bytes to be bytes and compute its exact SHA-256
3. require validation_input to be a mapping
4. freeze validation_input twice; require equal bounded immutable JSON/JCS snapshots
5. require every REPORT_CONSTRUCTABILITY_SHELLS path with its exact container type
6. extract and validate the trusted validation_context projection from the snapshot
```

Error-code selection follows that order. Independently, set
`input_payload_sha256` if and only if the candidate recipe value is actual
`bytes`, even when an earlier identity check selected the failure; hashing does
not alter error precedence.

The snapshot operation performs the Task 1 two-pass stability check and stores
only the accepted second `JsonSnapshot` in `ValidationInvocationContext`; it
never stores the caller's mapping. `REPORT_CONSTRUCTABILITY_SHELLS` is the exact
Section 4.1 path/type table:

```python
REPORT_CONSTRUCTABILITY_SHELLS = (
    ("/task_envelope", "object"),
    ("/authority_artifacts", "array"),
    ("/validation_context", "object"),
    ("/validation_context/environment_snapshots", "array"),
    ("/validation_context/policy_registries", "array"),
    ("/validation_context/payload_schema_registry", "object"),
    ("/validation_context/capability_registry", "object"),
    ("/validation_context/vocabularies", "object"),
    ("/validation_context/vocabularies/semantic_authority_codes", "object"),
    ("/validation_context/vocabularies/semantic_capability_codes", "object"),
    ("/validation_context/vocabularies/worker_slot_codes", "object"),
    ("/validation_context/vocabularies/semantic_materiality_codes", "object"),
    ("/validation_context/vocabularies/semantic_value_schemas", "object"),
)
```

Missing and wrong-type shells return the exact
constructability failures with the snapshot fingerprint and failing path.

The trusted projection contains valid `evaluated_at`, `trusted_clock_source`,
`task_session_id`, nullable `environment_session_id`, and
`capability_registry_session_id`. It is extracted only from a fresh thaw of the
accepted snapshot and ignores extra fields so the closed validation-input schema
can report them later. A missing trusted field returns
`trusted_validation_context_missing`; a malformed field returns
`trusted_validation_context_invalid`. No ledger, phase row, report fingerprint,
`valid`, or `compile_ready` value is constructed for any preflight failure. The
failure has `failure_stage="preflight"`; its message is fixed/bounded and
contains no raw exception text. Only a successful `ValidationInvocationContext`
may enter the phase pipeline.

The phase boundary is exact:

```text
schema:
  exact recipe bytes, JSON parsing/resource limits, and recipe product schema

companion_artifacts:
  validation-input envelope plus every supplied companion product schema,
  identity, fingerprint, freshness, session, registry, and vocabulary check
```

`parse_raw_json` resource-limit, bounded-number conversion, decoder-recursion,
and syntax outcomes are converted immediately to registered `schema`
diagnostics and a conforming report. They never escape as Python exceptions.
The `companion_artifacts` phase always evaluates its own thaw of the immutable
snapshot, even when recipe parsing or schema validation fails. A failed recipe
schema makes only `fingerprint` and semantic phases that depend on `schema`
`not_evaluated`. This permits one honest report to receipt independent recipe
and companion failures without speculating beyond either evaluated boundary.

Every phase runner receives a newly thawed tree from
`context.validation_input_snapshot`. No runner receives the original mapping,
the frozen internal tuples, or another runner's mutable tree. Report descriptors
and the validation-context fingerprint are derived from the snapshot and the
phase results, never by rereading caller state.

The public function must use this exact runner order after raw parsing, recipe
schema, fingerprint, and companion validation:

```python
SEMANTIC_PHASE_ORDER = (
    "provenance",
    "clause_graph",
    "derived_facts",
    "assumptions",
    "unresolved_intent",
    "shape",
    "capabilities",
    "worker_slots",
    "readiness",
)
```

Dispatch each name to the exact Task 5–7 function and preserve the returned
`PhaseIssues`. Before dispatch, consult `PHASE_DEPENDENCIES`; run phases whose
dependencies are `passed` or `blocked`, and record `not_evaluated` for a phase
with any failed/not-evaluated dependency without inventing speculative issues.
The orchestrator retains the assumption-authorization tuple for unresolved and
readiness phases and the semantic index for all semantic phases.

`planner_graph_recipe_validate.py` is the only production insertion point for
phase issues. Helpers return `PhaseIssues`; they never receive a
`ValidationLedger`. Immediately before each ledger insertion, the orchestrator
must validate the exact phase/code/classification tuple:

```python
def _insert_phase_issues(
    ledger: ValidationLedger,
    expected_phase: str,
    issues: PhaseIssues,
) -> None:
    for issue in issues.diagnostics:
        if issue.phase != expected_phase:
            raise RulesetIdentityError("ruleset_issue_phase_mismatch")
        assert_registered_issue(
            expected_phase,
            issue.code,
            "diagnostic",
            severity=issue.severity,
        )
        ledger.add_diagnostic(issue)
    for issue in issues.blockers:
        if issue.phase != expected_phase:
            raise RulesetIdentityError("ruleset_issue_phase_mismatch")
        assert_registered_issue(expected_phase, issue.code, "blocker")
        ledger.add_blocker(issue)
```

Raw/schema, fingerprint, and companion phases use the same insertion function;
there is no privileged path around the registry. `assert_registered_issue`
raises `ruleset_issue_code_unregistered` when the phase/code pair is absent and
`ruleset_issue_classification_mismatch` when the code exists for that phase
under the other issue class. A v1 diagnostic severity other than `error` raises
`ruleset_issue_severity_mismatch`. These are validator-integrity exceptions,
not report diagnostics. Unit helpers raise them for exact testing; the public
validator catches them before report publication and returns
`ValidationInvocationFailure(failure_stage="validation",
code="validator_integrity_failure")`. Any other ordinary `Exception` before a
complete report is published returns `validation / validator_internal_failure`
with a fixed bounded message and no exception text. Do not catch process-control
`BaseException` subclasses. Neither path emits a partial report.

Set:

```text
valid = no error diagnostics
compile_ready = valid and no compile blockers
```

If `valid` is false, do not speculate blockers from unevaluated phases.

- [ ] **Step 7: Implement recipe, validation-context, ruleset, and report fingerprint projections**

Recipe fingerprint: schema-normalize the complete recipe, remove only `recipe_fingerprint`, apply every set-order rule from spec Section 9, then `canonical_sha256`.

Validation-context fingerprint: build the exact Section 8.3 projection from descriptors, excluding derived statuses and entry counts, normalize/sort, then hash.

`recompute_validation_context_fingerprint(report)` is an independent audit
helper over the emitted report: it rebuilds that exact projection from the
report descriptors and validator identity, excludes the report's existing
`validation_context_fingerprint` field, normalizes under the same closed
projection schema, and hashes it. It must not return or trust the stored field.
The validator uses the same projection builder but the equality/tampering tests
invoke the recomputation helper separately after report emission.

Report fingerprint: normalize the complete closed report, remove only `report_fingerprint`, then hash. Keep claimed and computed recipe/companion fingerprints in distinct fields at every stage.

The validator identity values are fixed but are resolved during preflight:

```python
def resolve_validator_identity() -> Mapping[str, str]:
    verify_runtime_dependency_versions()
    return {
        "implementation_version": "lm9a.recipe_validator:v1",
        "ruleset_fingerprint": compute_ruleset_fingerprint(),
        "canonicalization_version": "rook.canonical_json:v1",
    }
```

Compute the `ruleset_fingerprint` value only through
`compute_ruleset_fingerprint()`. The versioned manifest binds schemas, phase
graph, ordering, vocabularies, every phase algorithm version and stable issue
code; the normalized source projection binds the actual production modules that
implement policy matching, provenance traversal, confirmation, readiness, and
the other semantic rules. A schema-only or phase-graph-only digest is forbidden.

- [ ] **Step 8: Run the complete unit-level LM9A gate**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_canonical.py `
  mcp_server/tests/test_planner_graph_recipe_schemas.py `
  mcp_server/tests/test_planner_graph_recipe_report.py `
  mcp_server/tests/test_planner_graph_recipe_authority.py `
  mcp_server/tests/test_planner_graph_recipe_semantics.py `
  mcp_server/tests/test_planner_graph_recipe_rules.py `
  mcp_server/tests/test_planner_graph_recipe_validate.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit the ruleset identity and validator entry point**

```powershell
git add mcp_server/src/rook/agent/planner_graph_recipe_rules.py `
  mcp_server/src/rook/agent/planner_graph_recipe_validate.py `
  mcp_server/tests/lm9a_contract_factory.py `
  mcp_server/tests/test_planner_graph_recipe_rules.py `
  mcp_server/tests/test_planner_graph_recipe_validate.py
git commit -m "feat(lm9a): bind ruleset identity and validation"
```

---

### Task 9: Canonical Radial Pair And Orthogonal Positive Fixtures

**Files:**
- Create: `mcp_server/tests/lm9a_fixture_factory.py`
- Create: `mcp_server/tests/test_lm9a_planner_graph_recipe_fixtures.py`

**Interfaces:**
- Consumes: public `validate_planner_graph_recipe` only.
- Produces test-only builders:
  - `radial_ready_fixture()`
  - `radial_unresolved_fixture()`
  - `radial_pair_manifest()`
  - `layer_control_fixture()`
  - `worker_slot_conformance_fixture()`
  - `confirmation_conformance_fixture()`
  - `pair_delta_ids(left_fixture, right_fixture) -> set[str]`
  - `run_fixture(fixture: tuple[bytes, Mapping[str, Any]]) -> Mapping[str, Any]`

- [ ] **Step 1: Build the radial ready/unresolved pair by stable identity**

The common task envelope supplies only:

```text
grid_count_x = 10
grid_count_y = 10
element_kind = boxes
radial_height_relationship = lowest near center and nondecreasing with radial distance
```

Both recipes share every companion, trusted validation time, vocabulary fingerprint, non-controlled assumption, and `worker_slots.entries: []`. The ready recipe has an explicit `assumption.grid_spacing` with typed value `2 model units`; the policy authorizes a range but contains no default or preferred value. The unresolved recipe removes that assumption and adds `unresolved.grid_spacing`.

The pair manifest must compare arrays by stable IDs and permit only:

```python
ALLOWED_PAIR_DIFFERENCES = {
    "assumption.grid_spacing",
    "unresolved.grid_spacing",
    "clause references affected by grid_spacing",
    "goal projection references affected by grid_spacing",
    "recipe_fingerprint",
}
```

Any other semantic delta fails the test.

- [ ] **Step 2: Add radial pair assertions**

```python
def test_radial_ready_and_unresolved_pair_have_controlled_outcomes():
    ready = run_fixture(radial_ready_fixture())
    unresolved = run_fixture(radial_unresolved_fixture())
    assert (ready["valid"], ready["compile_ready"]) == (True, True)
    assert (unresolved["valid"], unresolved["compile_ready"]) == (True, False)
    assert blocker_codes(unresolved) == {"unresolved_intent"}
    assert ready["computed_recipe_fingerprint"] != unresolved["computed_recipe_fingerprint"]
    delta = pair_delta_ids(radial_ready_fixture(), radial_unresolved_fixture())
    assert delta <= set(radial_pair_manifest()["allowed_recipe_differences"])
```

Also prove deterministic reruns under the same fixed clock, derived element count `100`, no workers, and invalidity if spacing is both supplied and unresolved.

- [ ] **Step 3: Add the non-radial layer control fixture**

Use exactly:

```text
Create a document layer named "Analysis".
Do not modify existing geometry or existing layers.
```

The recipe uses user facts, goal, maintains, one invariant, `manage_document_layers`, shape delegation, no assumptions, no unresolved intent, and no workers. Assert `valid=true` and `compile_ready=true`. Do not claim preventive invariant enforcement; LM9A validates declaration and authority only.

- [ ] **Step 4: Add the positive inert worker-slot fixture**

Declare one `author_formula_realization` slot, one exact `instantiate_worker_slot` delegate, one allowed output schema, legal input refs, and nonempty maintained support. Assert `valid=true`, `compile_ready=true`, and absence of any request, invocation, output, provider, or model artifact.

- [ ] **Step 5: Add the positive confirmation fixture**

Create a pre-receipt recipe whose one material assumption derives `confirmation_required`. Recompute the confirmation-subject fingerprint; issue a deterministic trusted same-session, unexpired receipt bound to the task envelope, assumption ID, complete typed-value fingerprint, and subject fingerprint; attach its reference and exact authority descriptor; restamp the ordinary recipe fingerprint. Assert derived status `confirmed`, `valid=true`, and `compile_ready=true`.

Also assert:

```text
subject before attachment == subject after attachment
ordinary recipe fingerprint before != ordinary recipe fingerprint after
semantic or policy change moves both subjects
```

- [ ] **Step 6: Run fixture tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_lm9a_planner_graph_recipe_fixtures.py -q
```

Expected: all fixtures pass with no model, worker, compiler, tool, or live process.

- [ ] **Step 7: Commit deterministic proof fixtures**

```powershell
git add mcp_server/tests/lm9a_fixture_factory.py `
  mcp_server/tests/test_lm9a_planner_graph_recipe_fixtures.py
git commit -m "test(lm9a): prove generic recipe fixtures"
```

---

### Task 10: Negative Matrix, Boundary Guards, And Final Offline Gate

**Files:**
- Create: `mcp_server/tests/test_lm9a_planner_graph_recipe_boundaries.py`
- Modify: focused LM9A tests only where a missing negative belongs beside its unit.

**Interfaces:**
- Consumes: all public LM9A modules and committed proof fixtures.
- Produces: deterministic structural evidence that LM9A remains generic, offline, and isolated from legacy protocols.

- [ ] **Step 1: Add the complete cross-cutting negative matrix**

Parameterize mutations of a known valid fixture for every spec Section 12.2 class not already asserted beside its unit. At minimum include:

```text
oversized/deep recipe input; missing/wrong report-constructability shells;
validation-input depth, repeated containers, unstable mappings, unsupported host values,
non-finite floats, and integers outside the finite JCS domain;
unknown fields; malformed IDs; duplicate IDs; dangling/mismatched refs;
numeric-token overflow and host numeric conversion failure;
URI-fragment and malformed pointers; duplicate members; bad payload schemas;
descriptor and fingerprint mismatches; context-fingerprint movement;
orphan requirements; unsupported derivations; policy no-match/overlap/prohibit;
receipt mismatch/expiry/session/revocation; invalid decimals/numbers;
unresolved conflicts; unknown shape/capability/slot codes;
one-way worker-slot links; deferred receipt kinds; recipe-fingerprint mismatch;
phase not_evaluated propagation; issue-classification collision.
```

Every report-producing parameter must assert exact `phase`, exact diagnostic or
blocker `code`, `valid`, and `compile_ready`; do not assert only that validation
failed. Every pre-report parameter must instead assert the exact
`ValidationInvocationFailure` stage, code, subject path, and fingerprint
presence rules, and must prove that no report fields exist.

Include vertical combined-failure cases, not only isolated mutations:

```text
malformed recipe + missing mandatory shell
  -> preflight constructability failure; no report

malformed recipe + present but malformed task companion
  -> one report with schema failed and companion_artifacts failed

malformed recipe + valid companions
  -> one report with schema failed and companion_artifacts passed

caller mapping changed after preflight
  -> report remains bound to the accepted immutable snapshot

one phase mutates its thawed tree
  -> later phases observe an independent thaw of the original snapshot
```

LM9A v1 has no separate revocation-registry companion. Trusted revocation is
represented by withdrawing the receipt from the trusted companion channel while
the recipe still cites it; the exact result is
`assumptions / confirmation_receipt_missing`. Do not invent a
`confirmation_receipt_revoked` report code or a new revocation artifact in this
slice.

- [ ] **Step 2: Add AST/source isolation guards**

```python
import ast
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
PRODUCTION_MODULES = tuple(
    ROOT.glob("mcp_server/src/rook/agent/planner_graph_recipe_*.py")
)


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def imported_module_names(paths):
    names = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


def called_names(paths):
    names = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                names.add(_dotted_name(node.func))
    return names


def test_lm9a_production_source_has_no_fixture_ontology():
    forbidden = (
        "radial",
        "box-array",
        "box_array",
        "box array",
        "grid-spacing",
        "grid_spacing",
        "height_falloff",
        "height-falloff",
    )
    rendered = "\n".join(path.read_text(encoding="utf-8").lower() for path in PRODUCTION_MODULES)
    assert all(marker not in rendered for marker in forbidden)


def test_lm9a_does_not_import_legacy_or_runtime_surfaces():
    forbidden_modules = {
        "rook.agent.plan_graph_workflow_contract",
        "rook.agent.planner_worker_contract_request",
        "rook.agent.planner",
        "rook.server",
    }
    imported = imported_module_names(PRODUCTION_MODULES)
    assert imported.isdisjoint(forbidden_modules)


def test_lm9a_source_has_no_model_tool_or_compiler_emission():
    forbidden_calls = {
        "run_two_pass_worker_publication",
        "call_rhino",
        "gh_edit",
        "dspy.Predict",
        "subprocess.run",
    }
    assert called_names(PRODUCTION_MODULES).isdisjoint(forbidden_calls)


def test_only_public_validator_inserts_production_phase_issues_into_ledger():
    ledger_writes = {"ledger.add_diagnostic", "ledger.add_blocker"}
    writers = {
        path.name
        for path in PRODUCTION_MODULES
        if called_names((path,)) & ledger_writes
    }
    assert writers == {"planner_graph_recipe_validate.py"}
```

Use AST visitors for imports and calls; use raw strings only for the fixture-ontology guard. Do not forbid words that appear legitimately in closed policy data or diagnostics.

- [ ] **Step 3: Add schema and fingerprint guards**

Prove:

- all product schemas remain closed and valid Draft 2020-12;
- all report artifacts validate under the report schema;
- no LM9A hash is bare or uppercase;
- exact JCS vectors remain green;
- no call/import/reference to `_fingerprint_normalized_contract` exists;
- raw-byte and normalized recipe hashes remain distinct;
- emitted validation-context fingerprints equal independent recomputation, and
  tampering with the stored context fingerprint produces inequality;
- every declared set-like collection appears in the normalization table and no array is dynamically inferred as a set.

- [ ] **Step 4: Run the focused LM9A gate**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_graph_recipe_canonical.py `
  mcp_server/tests/test_planner_graph_recipe_schemas.py `
  mcp_server/tests/test_planner_graph_recipe_report.py `
  mcp_server/tests/test_planner_graph_recipe_authority.py `
  mcp_server/tests/test_planner_graph_recipe_semantics.py `
  mcp_server/tests/test_planner_graph_recipe_rules.py `
  mcp_server/tests/test_planner_graph_recipe_validate.py `
  mcp_server/tests/test_lm9a_planner_graph_recipe_fixtures.py `
  mcp_server/tests/test_lm9a_planner_graph_recipe_boundaries.py -q
```

Expected: all LM9A tests pass.

- [ ] **Step 5: Run nearby regression gates**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_planner_worker_contract_request.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  mcp_server/tests/test_validation.py -q

.\mcp_server\.venv\Scripts\python.exe -m py_compile `
  mcp_server/src/rook/agent/planner_graph_recipe_canonical.py `
  mcp_server/src/rook/agent/planner_graph_recipe_schemas.py `
  mcp_server/src/rook/agent/planner_graph_recipe_report.py `
  mcp_server/src/rook/agent/planner_graph_recipe_authority.py `
  mcp_server/src/rook/agent/planner_graph_recipe_semantics.py `
  mcp_server/src/rook/agent/planner_graph_recipe_rules.py `
  mcp_server/src/rook/agent/planner_graph_recipe_validate.py

git diff --check origin/main...HEAD
```

Expected: all tests and compilation pass; diff check is clean.

- [ ] **Step 6: Verify exact scope and absence of live artifacts**

```powershell
git diff --name-only origin/main...HEAD
git status --short
```

Expected tracked scope: LM9A spec/plan plus the production/test/dependency files named in this plan. No `probe_runs/`, Rhino/GH artifacts, generated reports, model output, knowledge drift, or unrelated docs are staged.

- [ ] **Step 7: Commit final guards**

```powershell
git add mcp_server/tests/test_lm9a_planner_graph_recipe_boundaries.py `
  mcp_server/tests/test_planner_graph_recipe_canonical.py `
  mcp_server/tests/test_planner_graph_recipe_schemas.py `
  mcp_server/tests/test_planner_graph_recipe_report.py `
  mcp_server/tests/test_planner_graph_recipe_authority.py `
  mcp_server/tests/test_planner_graph_recipe_semantics.py `
  mcp_server/tests/test_planner_graph_recipe_rules.py `
  mcp_server/tests/test_planner_graph_recipe_validate.py `
  mcp_server/tests/test_lm9a_planner_graph_recipe_fixtures.py
git commit -m "test(lm9a): lock recipe validator boundaries"
```

---

## Final Review Checklist

- [ ] Every requirement implemented now in spec Section 3.1 has a production task and a positive proof.
- [ ] Every future-only item in spec Section 3.2 remains absent from production code.
- [ ] Exact RFC 8785 vectors, UTF-16 ordering, raw-byte parsing, decimal identity, and confirmation projection have focused tests.
- [ ] Raw recipe ingress emits reports at the exact 1 MiB/64-container bounds, including decoder-recursion inputs.
- [ ] Numeric ingress uses bounded integer/float callbacks, rejects overflow and oversized tokens deterministically, and the iterative companion walk rejects non-finite values even inside schema documents.
- [ ] Invocation preflight proves every pre-report failure path without constructing a partial report; envelope errors remain reportable only when trusted context survives.
- [ ] Post-preflight integrity assertions and implementation exceptions return typed validation-stage invocation failures rather than partial reports or leaked exceptions.
- [ ] Recipe schema failures belong only to `schema`; validation-input and companion structural failures belong only to `companion_artifacts`.
- [ ] The recipe, report, validation input, companions, descriptors, and vocabularies are all closed schemas.
- [ ] `valid` and `compile_ready` derive mechanically and remain semantically distinct.
- [ ] Blocked phase dependencies remain evaluable; failed/not-evaluated dependencies suppress dependent phases.
- [ ] Companion fingerprints, recipe fingerprints, validation-context fingerprints, and report fingerprints remain distinct and independently recomputable.
- [ ] The public orchestrator rejects unregistered, misclassified, and wrong-severity phase issues before ledger insertion.
- [ ] The ready/unresolved pair differs only under its test-only stable-ID allowlist.
- [ ] The non-radial fixture proves the validator is not radial-family machinery.
- [ ] The positive worker-slot fixture never instantiates a request.
- [ ] The positive confirmation fixture proves subject-fingerprint stability without a hash cycle.
- [ ] No existing Planner/worker/workflow contract file is modified.
- [ ] No live test or model invocation occurs in the implementation PR.
