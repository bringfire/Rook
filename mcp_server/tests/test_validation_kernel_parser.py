from __future__ import annotations

import inspect
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

import pytest

import rook.validation_kernel.parser as PARSER_MODULE
from rook.validation_kernel.budget import (
    BudgetExceeded,
    BudgetLedger,
    LM9A_BUDGET_MANIFEST,
)
from rook.validation_kernel.canonical_json import canonical_json_bytes
from rook.validation_kernel.control import ArtifactRole, BudgetDimension
from rook.validation_kernel.owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    count_json_nodes,
    own_trusted_json,
)
from rook.validation_kernel.parser import JsonParseError, parse_owned_json


FIXTURES = Path(__file__).parent / "fixtures" / "validation_kernel"
RNG_SEED = 0x4C4D3941
VALID_DOCUMENT_COUNT = 5_000
MUTATED_DOCUMENT_COUNT = 15_000
MAX_GENERATED_DEPTH = 8
MAX_GENERATED_WIDTH = 8

_DIRECTED_VALID_DOCUMENTS = {
    "null": b"null",
    "true": b"true",
    "false": b"false",
    "zero_integer": b"0",
    "negative_integer": b"-123",
    "fraction": b"-12.50",
    "exponent_lower": b"1e-10",
    "exponent_upper_signed": b"1E+10",
    "empty_string": b'""',
    "simple_escapes": b'"\\\"\\\\\\/\\b\\f\\n\\r\\t"',
    "unicode_escape": b'"\\u20ac"',
    "surrogate_pair": b'"\\uD83D\\uDE00"',
    "raw_unicode": '"euro=\u20ac emoji=\U0001f600"'.encode("utf-8"),
    "whitespace": b" \t\r\n[ true , false , null ] \n",
    "empty_array": b"[]",
    "empty_object": b"{}",
    "all_structural_tokens": b'{"a":[null,true,false,0,"x"],"b":{}}',
    "depth_eight": b"[" * 8 + b"null" + b"]" * 8,
    "array_width_eight": b"[0,1,2,3,4,5,6,7]",
    "object_width_eight": b'{"a":0,"b":1,"c":2,"d":3,"e":4,"f":5,"g":6,"h":7}',
}
_REQUIRED_VALID_PRODUCTIONS = frozenset(_DIRECTED_VALID_DOCUMENTS)

_MUTATION_FAMILIES = (
    "delimiter_deletion",
    "truncation",
    "trailing_comma",
    "colon_comma_substitution",
    "duplicate_key_insertion",
    "invalid_escape",
    "malformed_exponent_or_leading_zero",
    "extra_root_token",
    "invalid_or_truncated_utf8",
)


class _OracleRejected(ValueError):
    pass


def _limit(dimension: BudgetDimension) -> int:
    return int(LM9A_BUDGET_MANIFEST.limits[dimension.value].value)


def _new_ledger() -> BudgetLedger:
    return BudgetLedger(LM9A_BUDGET_MANIFEST)


def _parse(
    raw: bytes,
    *,
    ledger: BudgetLedger | None = None,
    artifact_role: str = ArtifactRole.RECIPE.value,
):
    return parse_owned_json(
        raw,
        artifact_role=artifact_role,
        ledger=_new_ledger() if ledger is None else ledger,
    )


def _parse_rejection(raw: bytes) -> JsonParseError:
    with pytest.raises(JsonParseError) as raised:
        _parse(raw)
    return raised.value


def test_parser_accepts_only_exact_builtin_bytes() -> None:
    class BytesSubclass(bytes):
        pass

    for raw in (
        bytearray(b"null"),
        memoryview(b"null"),
        BytesSubclass(b"null"),
        "null",
    ):
        with pytest.raises(TypeError):
            parse_owned_json(
                raw,  # type: ignore[arg-type]
                artifact_role=ArtifactRole.RECIPE.value,
                ledger=_new_ledger(),
            )


def test_parser_rejects_bom_and_invalid_or_truncated_utf8() -> None:
    cases = (
        (b"\xef\xbb\xbfnull", "bom_not_allowed"),
        (b"\xff", "invalid_utf8"),
        (b"null\xff", "invalid_utf8"),
        (b'"\xff"', "invalid_utf8"),
        (b'"\xc0\x80"', "invalid_utf8"),
        (b'"\xe2\x82"', "invalid_utf8"),
        (b'"\xed\xa0\x80"', "invalid_utf8"),
        (b'"\xf4\x90\x80\x80"', "invalid_utf8"),
    )

    for raw, category in cases:
        error = _parse_rejection(raw)
        assert error.evidence.category == category
        assert error.evidence.artifact_role == ArtifactRole.RECIPE.value
        assert error.evidence.subject_path is None
        assert len(error.evidence.bounded_message) <= 512
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", error.evidence.detail_sha256)
        assert raw.hex() not in repr(error)


def test_parser_rejects_duplicate_members_before_canonical_sorting() -> None:
    for raw in (
        b'{"x":1,"x":2}',
        '{"\U0001f600":1,"\\uD83D\\uDE00":2}'.encode("utf-8"),
    ):
        assert _parse_rejection(raw).evidence.category == "duplicate_member"


@pytest.mark.parametrize(
    "raw",
    [
        b'"\\uD800"',
        b'"\\uDE00"',
        b'"\\uD800\\u0041"',
        b'"\\uD800\\uD800"',
        b'"\\uDE00\\uD800"',
    ],
)
def test_parser_rejects_unpaired_or_incorrectly_paired_surrogates(raw: bytes) -> None:
    assert _parse_rejection(raw).evidence.category == "invalid_surrogate"


def test_parser_accepts_container_depth_64_and_rejects_65_before_node_charge() -> None:
    at_limit = b"[" * 64 + b"0" + b"]" * 64
    ledger = _new_ledger()

    parsed = _parse(at_limit, ledger=ledger)

    assert count_json_nodes(parsed.value) == 65
    assert ledger.snapshot().maximum_container_depth == 64

    over_limit = b"[" * 65 + b"0" + b"]" * 65
    over_ledger = _new_ledger()
    with pytest.raises(BudgetExceeded) as raised:
        _parse(over_limit, ledger=over_ledger)

    assert raised.value.failure.budget_dimension == "container_depth"
    assert raised.value.failure.artifact_role == ArtifactRole.RECIPE.value
    assert raised.value.failure.limit == 64
    assert raised.value.failure.observed_lower_bound == 65
    assert over_ledger.snapshot().parsed_nodes == 64


def _array_with_width(width: int) -> bytes:
    return b"[" + b",".join(b"null" for _ in range(width)) + b"]"


def _object_with_width(width: int) -> bytes:
    return (
        b"{"
        + b",".join(f'"k{index}":null'.encode("ascii") for index in range(width))
        + b"}"
    )


@pytest.mark.parametrize(
    ("dimension", "builder", "snapshot_field"),
    [
        (BudgetDimension.ARRAY_ITEMS, _array_with_width, "maximum_array_items"),
        (BudgetDimension.OBJECT_MEMBERS, _object_with_width, "maximum_object_members"),
    ],
)
def test_container_width_limit_is_inclusive_and_charged_before_next_value(
    dimension: BudgetDimension,
    builder,
    snapshot_field: str,
) -> None:
    limit = _limit(dimension)
    ledger = _new_ledger()

    parsed = _parse(builder(limit), ledger=ledger)

    assert len(parsed.value) == limit
    assert getattr(ledger.snapshot(), snapshot_field) == limit

    over_ledger = _new_ledger()
    with pytest.raises(BudgetExceeded) as raised:
        _parse(builder(limit + 1), ledger=over_ledger)

    assert raised.value.failure.budget_dimension == dimension.value
    assert raised.value.failure.artifact_role == ArtifactRole.RECIPE.value
    assert raised.value.failure.observed_lower_bound == limit + 1
    assert getattr(over_ledger.snapshot(), snapshot_field) == limit
    assert over_ledger.snapshot().parsed_nodes == limit + 1


def test_shared_parsed_node_budget_accepts_exact_limit_and_rejects_next_node() -> None:
    limit = _limit(BudgetDimension.PARSED_NODES)
    exact_ledger = _new_ledger()
    exact_ledger.charge(
        BudgetDimension.PARSED_NODES,
        limit - 1,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )

    _parse(b"null", ledger=exact_ledger)

    assert exact_ledger.snapshot().parsed_nodes == limit

    over_ledger = _new_ledger()
    over_ledger.charge(
        BudgetDimension.PARSED_NODES,
        limit,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )
    with pytest.raises(BudgetExceeded) as raised:
        _parse(b"null", ledger=over_ledger)

    assert raised.value.failure.budget_dimension == "parsed_nodes"
    assert raised.value.failure.artifact_role == ArtifactRole.COMBINED.value
    assert raised.value.failure.observed_lower_bound == limit + 1


def test_shared_decoded_string_budget_charges_before_string_node_allocation() -> None:
    limit = _limit(BudgetDimension.DECODED_STRING_BYTES)
    exact_ledger = _new_ledger()
    exact_ledger.charge(
        BudgetDimension.DECODED_STRING_BYTES,
        limit - 1,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )

    parsed = _parse(b'"x"', ledger=exact_ledger)

    assert parsed.value.value == "x"
    assert exact_ledger.snapshot().decoded_string_bytes == limit

    over_ledger = _new_ledger()
    over_ledger.charge(
        BudgetDimension.DECODED_STRING_BYTES,
        limit,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )
    with pytest.raises(BudgetExceeded) as raised:
        _parse(b'"x"', ledger=over_ledger)

    assert raised.value.failure.budget_dimension == "decoded_string_bytes"
    assert raised.value.failure.artifact_role == ArtifactRole.COMBINED.value
    assert raised.value.failure.observed_lower_bound == limit + 1
    assert over_ledger.snapshot().parsed_nodes == 0


def test_shared_parser_work_budget_counts_blocks_tokens_nodes_and_attachments() -> None:
    limit = _limit(BudgetDimension.PARSER_WORK_UNITS)
    exact_ledger = _new_ledger()
    exact_ledger.charge(
        BudgetDimension.PARSER_WORK_UNITS,
        limit - 3,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )

    _parse(b"null", ledger=exact_ledger)

    assert exact_ledger.snapshot().parser_work_units == limit

    over_ledger = _new_ledger()
    over_ledger.charge(
        BudgetDimension.PARSER_WORK_UNITS,
        limit - 2,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )
    with pytest.raises(BudgetExceeded) as raised:
        _parse(b"null", ledger=over_ledger)

    assert raised.value.failure.budget_dimension == "parser_work_units"
    assert raised.value.failure.artifact_role == ArtifactRole.COMBINED.value
    assert raised.value.failure.observed_lower_bound == limit + 1
    assert over_ledger.snapshot().parsed_nodes == 0


@pytest.mark.parametrize(
    ("raw", "constructor_name"),
    [(b"null", "JsonNull"), (b"true", "JsonBoolean"), (b"false", "JsonBoolean")],
)
def test_literal_node_budget_is_charged_before_scalar_construction(
    raw: bytes,
    constructor_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _new_ledger()
    ledger.charge(
        BudgetDimension.PARSED_NODES,
        _limit(BudgetDimension.PARSED_NODES),
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )

    def unexpected_constructor(*args: object) -> object:
        raise AssertionError("literal constructor ran before node admission")

    monkeypatch.setattr(PARSER_MODULE, constructor_name, unexpected_constructor)
    with pytest.raises(BudgetExceeded) as raised:
        _parse(raw, ledger=ledger)

    assert raised.value.failure.budget_dimension == "parsed_nodes"
    assert raised.value.failure.observed_lower_bound == (
        _limit(BudgetDimension.PARSED_NODES) + 1
    )


def test_parser_work_counts_started_raw_blocks_and_structural_attachments_exactly() -> None:
    cases = (
        (b"null" + b" " * 60, 3),
        (b"null" + b" " * 61, 4),
        (b"[null]", 7),
        (b'{"a":null}', 9),
    )

    for raw, expected_work in cases:
        ledger = _new_ledger()
        _parse(raw, ledger=ledger)
        assert ledger.snapshot().parser_work_units == expected_work


def test_number_token_character_limit_is_inclusive() -> None:
    exact = b"0." + b"0" * 1_022
    assert len(exact) == 1_024
    ledger = _new_ledger()

    parsed = _parse(exact, ledger=ledger)

    assert isinstance(parsed.value, JsonNumber)
    assert parsed.value.value == 0.0
    assert parsed.value.source_token_classification == "fraction"
    assert ledger.snapshot().maximum_number_token_chars == 1_024

    over = exact + b"0"
    over_ledger = _new_ledger()
    with pytest.raises(BudgetExceeded) as raised:
        _parse(over, ledger=over_ledger)

    assert raised.value.failure.budget_dimension == "number_token_chars"
    assert raised.value.failure.artifact_role == ArtifactRole.RECIPE.value
    assert raised.value.failure.limit == 1_024
    assert raised.value.failure.observed_lower_bound == 1_025
    assert over_ledger.snapshot().parsed_nodes == 0


def test_overflow_and_very_long_numbers_are_rejected() -> None:
    for raw in (b"1e10000", b"-1e10000"):
        assert _parse_rejection(raw).evidence.category == "nonfinite_number"

    with pytest.raises(BudgetExceeded) as raised:
        _parse(b"9" * 5_000)
    assert raised.value.failure.budget_dimension == "number_token_chars"
    assert raised.value.failure.observed_lower_bound == 1_025


@pytest.mark.parametrize("raw", [b"NaN", b"Infinity", b"-Infinity"])
def test_nonfinite_literal_spellings_are_rejected(raw: bytes) -> None:
    with pytest.raises(JsonParseError):
        _parse(raw)


def test_parser_accepts_escapes_surrogate_pairs_and_all_structural_tokens() -> None:
    raw = (
        b'{"array":[null,true,false,-12,1.25,2e3],'
        b'"controls":"\\b\\f\\n\\r\\t",'
        b'"pair":"\\uD83D\\uDE00",'
        b'"quote":"\\\"",'
        b'"raw":"\xe2\x82\xac",'
        b'"slash":"\\\\\\/"}'
    )

    parsed = _parse(raw)

    assert isinstance(parsed.value, JsonObject)
    assert isinstance(parsed.value["array"], JsonArray)
    assert isinstance(parsed.value["array"][0], JsonNull)
    assert isinstance(parsed.value["array"][1], JsonBoolean)
    assert parsed.value["array"][3].source_token_classification == "integer"
    assert parsed.value["array"][4].source_token_classification == "fraction"
    assert parsed.value["array"][5].source_token_classification == "exponent"
    assert parsed.value["controls"].value == "\b\f\n\r\t"
    assert parsed.value["pair"].value == "\U0001f600"
    assert parsed.value["quote"].value == '"'
    assert parsed.value["raw"].value == "\u20ac"
    assert parsed.value["slash"].value == "\\/"


def test_object_source_order_does_not_change_canonical_identity() -> None:
    first = _parse(b'{"b":2,"a":1}')
    second = _parse(b'{"a":1,"b":2}')

    assert first.value_fingerprint == second.value_fingerprint
    assert canonical_json_bytes(first.value) == b'{"a":1,"b":2}'
    assert canonical_json_bytes(second.value) == b'{"a":1,"b":2}'


def test_hand_curated_parser_corpus() -> None:
    rows = [
        json.loads(line)
        for line in (FIXTURES / "parser_corpus.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert rows
    assert len({row["name"] for row in rows}) == len(rows)
    for row in rows:
        raw = bytes.fromhex(row["raw_hex"])
        if row["accepted"]:
            parsed = _parse(raw)
            assert parsed.value_fingerprint == row["expected_fingerprint"], row["name"]
        else:
            error = _parse_rejection(raw)
            assert error.evidence.category == row["category"], row["name"]


def _normalize_oracle_string(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        code_point = ord(value[index])
        if 0xD800 <= code_point <= 0xDBFF:
            if index + 1 == len(value):
                raise _OracleRejected("unpaired high surrogate")
            low = ord(value[index + 1])
            if not 0xDC00 <= low <= 0xDFFF:
                raise _OracleRejected("incorrect surrogate pair")
            output.append(chr(0x10000 + ((code_point - 0xD800) << 10) + low - 0xDC00))
            index += 2
            continue
        if 0xDC00 <= code_point <= 0xDFFF:
            raise _OracleRejected("unpaired low surrogate")
        output.append(value[index])
        index += 1
    return "".join(output)


def _oracle_pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
    normalized_pairs = [(_normalize_oracle_string(key), value) for key, value in pairs]
    names: set[str] = set()
    for key, _ in normalized_pairs:
        if key in names:
            raise _OracleRejected("duplicate member")
        names.add(key)
    return dict(normalized_pairs)


def _reject_constant(_: str) -> object:
    raise _OracleRejected("nonfinite literal")


def _strict_oracle(raw: bytes) -> tuple[bool, object | None]:
    try:
        text = raw.decode("utf-8", errors="strict")
        if text.startswith("\ufeff"):
            raise _OracleRejected("BOM")
        root = json.loads(
            text,
            parse_constant=_reject_constant,
            object_pairs_hook=_oracle_pairs_hook,
        )

        stack: list[tuple[object | None, object | None, object]] = [(None, None, root)]
        while stack:
            parent, slot, current = stack.pop()
            if type(current) is float and not math.isfinite(current):
                raise _OracleRejected("nonfinite conversion")
            if type(current) is str:
                normalized = _normalize_oracle_string(current)
                if parent is None:
                    root = normalized
                elif type(parent) is list:
                    parent[slot] = normalized
                else:
                    parent[slot] = normalized
                continue
            if type(current) is list:
                stack.extend((current, index, value) for index, value in enumerate(current))
                continue
            if type(current) is dict:
                stack.extend((current, key, value) for key, value in current.items())
        return True, root
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _OracleRejected,
        OverflowError,
        ValueError,
    ):
        return False, None


def _oracle_shape(root: object) -> tuple[int, int]:
    maximum_depth = 0
    maximum_width = 0
    stack: list[tuple[object, int]] = [(root, 0)]
    while stack:
        current, parent_depth = stack.pop()
        if type(current) is list:
            depth = parent_depth + 1
            maximum_depth = max(maximum_depth, depth)
            maximum_width = max(maximum_width, len(current))
            stack.extend((value, depth) for value in current)
        elif type(current) is dict:
            depth = parent_depth + 1
            maximum_depth = max(maximum_depth, depth)
            maximum_width = max(maximum_width, len(current))
            stack.extend((value, depth) for value in current.values())
    return maximum_depth, maximum_width


def _random_string_token(rng: random.Random) -> bytes:
    pieces = (
        b"ascii",
        b" ",
        b"\\\"",
        b"\\\\",
        b"\\/",
        b"\\b",
        b"\\f",
        b"\\n",
        b"\\r",
        b"\\t",
        b"\\u0000",
        b"\\u20ac",
        b"\\uD83D\\uDE00",
        "\u00e9".encode("utf-8"),
        "\U0001f642".encode("utf-8"),
    )
    return b'"' + b"".join(rng.choice(pieces) for _ in range(rng.randrange(0, 6))) + b'"'


def _random_number_token(rng: random.Random) -> bytes:
    production = rng.randrange(3)
    sign = b"-" if rng.randrange(2) else b""
    integer = str(rng.randrange(0, 1_000_000)).encode("ascii")
    if production == 0:
        return sign + integer
    if production == 1:
        return sign + integer + b"." + str(rng.randrange(0, 1_000_000)).zfill(6).encode("ascii")
    exponent_marker = b"e" if rng.randrange(2) else b"E"
    exponent_sign = rng.choice((b"", b"+", b"-"))
    exponent = str(rng.randrange(0, 21)).encode("ascii")
    return sign + integer + exponent_marker + exponent_sign + exponent


def _random_scalar(rng: random.Random) -> bytes:
    choice = rng.randrange(6)
    if choice == 0:
        return b"null"
    if choice == 1:
        return b"true"
    if choice == 2:
        return b"false"
    if choice == 3:
        return _random_number_token(rng)
    return _random_string_token(rng)


def _random_value(rng: random.Random, depth: int) -> bytes:
    if depth >= MAX_GENERATED_DEPTH or rng.randrange(4) != 0:
        return _random_scalar(rng)

    width = rng.randrange(0, 4)
    if rng.randrange(2) == 0:
        return b"[" + b",".join(_random_value(rng, depth + 1) for _ in range(width)) + b"]"

    members: list[bytes] = []
    for index in range(width):
        generated_key = _random_string_token(rng)
        unique_key = b'"k' + str(index).encode("ascii") + b":" + generated_key[1:]
        members.append(unique_key + b":" + _random_value(rng, depth + 1))
    return b"{" + b",".join(members) + b"}"


def _valid_documents() -> tuple[list[bytes], frozenset[str]]:
    rng = random.Random(RNG_SEED)
    documents = list(_DIRECTED_VALID_DOCUMENTS.values())
    while len(documents) < VALID_DOCUMENT_COUNT:
        documents.append(_random_value(rng, 0))
    return documents, frozenset(_DIRECTED_VALID_DOCUMENTS)


def _mutate(family: str, base: bytes, index: int) -> bytes:
    if family == "delimiter_deletion":
        return b"[" + base
    if family == "truncation":
        return base[: max(0, len(base) // 2)]
    if family == "trailing_comma":
        return b"[" + base + b",]"
    if family == "colon_comma_substitution":
        return b'{"x",' + base + b"}"
    if family == "duplicate_key_insertion":
        return b'{"duplicate":' + base + b',"duplicate":null}'
    if family == "invalid_escape":
        return b'["\\x",' + base + b"]"
    if family == "malformed_exponent_or_leading_zero":
        malformed = b"01" if index % 2 else b"1e+"
        return b"[" + malformed + b"," + base + b"]"
    if family == "extra_root_token":
        return base + b" null"
    if family == "invalid_or_truncated_utf8":
        invalid = b"\xff" if index % 2 else b"\xe2\x82"
        return b'["' + invalid + b'",' + base + b"]"
    raise AssertionError(f"unknown mutation family: {family}")


def test_fixed_seed_grammar_differential_matches_strict_duplicate_aware_oracle() -> None:
    valid_documents, covered_productions = _valid_documents()

    assert len(valid_documents) == VALID_DOCUMENT_COUNT
    assert covered_productions == _REQUIRED_VALID_PRODUCTIONS
    for name, raw in _DIRECTED_VALID_DOCUMENTS.items():
        oracle_accepted, _ = _strict_oracle(raw)
        assert oracle_accepted, name

    mutation_counts: Counter[str] = Counter()
    oracle_rejections: Counter[str] = Counter()
    mutated_documents: list[tuple[str, bytes]] = []
    for index in range(MUTATED_DOCUMENT_COUNT):
        family = _MUTATION_FAMILIES[index % len(_MUTATION_FAMILIES)]
        candidate = _mutate(family, valid_documents[index % len(valid_documents)], index)
        mutation_counts[family] += 1
        mutated_documents.append((family, candidate))

    assert len(mutated_documents) == MUTATED_DOCUMENT_COUNT
    assert set(mutation_counts) == set(_MUTATION_FAMILIES)
    assert sum(mutation_counts.values()) == MUTATED_DOCUMENT_COUNT

    cases = [("valid", raw) for raw in valid_documents] + mutated_documents
    assert len(cases) == VALID_DOCUMENT_COUNT + MUTATED_DOCUMENT_COUNT
    observed_valid_depth = 0
    observed_valid_width = 0
    for case_index, (family, raw) in enumerate(cases):
        oracle_accepted, oracle_value = _strict_oracle(raw)
        if family == "valid":
            assert oracle_accepted, (case_index, raw[:256])
            depth, width = _oracle_shape(oracle_value)
            observed_valid_depth = max(observed_valid_depth, depth)
            observed_valid_width = max(observed_valid_width, width)
        if family != "valid" and not oracle_accepted:
            oracle_rejections[family] += 1

        try:
            parsed = _parse(raw)
        except (JsonParseError, BudgetExceeded):
            parser_accepted = False
            parsed = None
        else:
            parser_accepted = True

        assert parser_accepted == oracle_accepted, (
            case_index,
            family,
            raw[:256],
        )
        if parser_accepted:
            assert parsed is not None
            oracle_owned = own_trusted_json(oracle_value)
            assert canonical_json_bytes(parsed.value) == canonical_json_bytes(oracle_owned)
            assert count_json_nodes(parsed.value) == count_json_nodes(oracle_owned)

    assert observed_valid_depth == MAX_GENERATED_DEPTH
    assert observed_valid_width == MAX_GENERATED_WIDTH
    assert set(oracle_rejections) == set(_MUTATION_FAMILIES)
    assert all(oracle_rejections[family] >= 1 for family in _MUTATION_FAMILIES)


def test_production_parser_does_not_delegate_to_host_json_decoder() -> None:
    source = inspect.getsource(PARSER_MODULE)
    lowered = source.lower()

    assert "json.loads" not in source
    assert "literal_eval" not in source
    assert "import json" not in source
    assert "yaml" not in lowered
    assert "orjson" not in lowered
    assert "rapidjson" not in lowered
    assert "_strict_oracle" not in source
    assert "_valid_documents" not in source
