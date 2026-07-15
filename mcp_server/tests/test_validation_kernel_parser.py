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
_MAXIMUM_FINITE = float.fromhex("0x1.fffffffffffffp+1023")
_MINIMUM_NORMAL = float.fromhex("0x1.0000000000000p-1022")
_MINIMUM_SUBNORMAL = float.fromhex("0x0.0000000000001p-1022")
_MAXIMUM_FINITE_INTEGER_TOKEN = str(int(_MAXIMUM_FINITE)).encode("ascii")
_ACCEPTED_BINARY64_BOUNDARIES = (
    (b"1.7976931348623157e308", _MAXIMUM_FINITE),
    (_MAXIMUM_FINITE_INTEGER_TOKEN, _MAXIMUM_FINITE),
    (b"2.2250738585072014e-308", _MINIMUM_NORMAL),
    (b"4.9406564584124654e-324", _MINIMUM_SUBNORMAL),
    (b"2e-324", 0.0),
    (b"9007199254740991", float(2**53 - 1)),
    (b"9007199254740992", float(2**53)),
    (b"9007199254740993", float(2**53)),
    (b"1.0000000000000001", 1.0),
    (b"1.0000000000000002", math.nextafter(1.0, math.inf)),
)
_BASIC_GENERATED_NUMBER_TOKENS = (
    b"0",
    b"-0",
    b"1",
    b"-1",
    b"1.5",
    b"1e10",
    b"1E+10",
    b"1e-10",
)
_GENERATED_NUMBER_BOUNDARY_CHOICES = _BASIC_GENERATED_NUMBER_TOKENS + tuple(
    raw for raw, _ in _ACCEPTED_BINARY64_BOUNDARIES
)
_REQUIRED_GENERATED_NUMBER_TOKENS = frozenset(
    _BASIC_GENERATED_NUMBER_TOKENS + _GENERATED_NUMBER_BOUNDARY_CHOICES
)
_REQUIRED_GENERATED_STRING_FORMS = (
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


class _OracleRejected(ValueError):
    """The independent parser oracle rejected the candidate input."""


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
        """An inexact byte carrier used to probe the public boundary."""

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
        limit - 4,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )

    _parse(b"null", ledger=exact_ledger)

    assert exact_ledger.snapshot().parser_work_units == limit

    over_ledger = _new_ledger()
    over_ledger.charge(
        BudgetDimension.PARSER_WORK_UNITS,
        limit - 3,
        artifact_role=ArtifactRole.COMBINED,
        subject_path=None,
    )
    with pytest.raises(BudgetExceeded) as raised:
        _parse(b"null", ledger=over_ledger)

    assert raised.value.failure.budget_dimension == "parser_work_units"
    assert raised.value.failure.artifact_role == ArtifactRole.COMBINED.value
    assert raised.value.failure.observed_lower_bound == limit + 1
    assert over_ledger.snapshot().parsed_nodes == 1


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
        (b"null" + b" " * 60, 4),
        (b"null" + b" " * 61, 5),
        (b"[null]", 8),
        (b'{"a":null}', 10),
    )

    for raw, expected_work in cases:
        ledger = _new_ledger()
        _parse(raw, ledger=ledger)
        assert ledger.snapshot().parser_work_units == expected_work


@pytest.mark.parametrize(
    ("raw", "expected_work"),
    (
        (b'"' + b"a" * 62 + b'"', 4),
        (b'"' + b"a" * 63 + b'"', 6),
    ),
)
def test_parser_fingerprint_charges_each_started_canonical_output_block(
    raw: bytes,
    expected_work: int,
) -> None:
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
            if type(current) is int:
                try:
                    binary64 = float(current)
                except OverflowError:
                    raise _OracleRejected("integer outside binary64 domain") from None
                if not math.isfinite(binary64):
                    raise _OracleRejected("integer outside binary64 domain")
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


@pytest.mark.parametrize(("raw", "expected"), _ACCEPTED_BINARY64_BOUNDARIES)
def test_parser_and_oracle_accept_exact_binary64_boundaries(
    raw: bytes,
    expected: float,
) -> None:
    assert len(raw) <= _limit(BudgetDimension.NUMBER_TOKEN_CHARS)
    oracle_accepted, oracle_value = _strict_oracle(raw)

    assert oracle_accepted
    parsed = _parse(raw)
    assert isinstance(parsed.value, JsonNumber)
    assert parsed.value.value == expected
    oracle_owned = own_trusted_json(oracle_value)
    assert canonical_json_bytes(parsed.value) == canonical_json_bytes(oracle_owned)


@pytest.mark.parametrize(
    "raw",
    [b"1.7976931348623159e308", b"9" * 309],
    ids=("exponent_overflow", "integer_overflow"),
)
def test_parser_and_oracle_reject_binary64_overflow_within_token_cap(raw: bytes) -> None:
    assert len(raw) <= _limit(BudgetDimension.NUMBER_TOKEN_CHARS)

    oracle_accepted, _ = _strict_oracle(raw)

    assert not oracle_accepted
    assert _parse_rejection(raw).evidence.category == "nonfinite_number"


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
    production = rng.randrange(5)
    sign = b"-" if rng.randrange(2) else b""
    if production == 0:
        return rng.choice(_GENERATED_NUMBER_BOUNDARY_CHOICES)
    if production == 1:
        digit_count = rng.choice((1, 2, 16, 17, 53, 100, 200, 308))
        first = str(rng.randrange(1, 10))
        remaining = "".join(
            str(rng.randrange(10)) for _ in range(digit_count - 1)
        )
        return sign + (first + remaining).encode("ascii")
    if production == 2:
        integer = str(rng.randrange(0, 1_000_000)).encode("ascii")
        fraction = str(rng.randrange(0, 10**16)).zfill(16).encode("ascii")
        return sign + integer + b"." + fraction

    coefficient = (
        f"{rng.randrange(1, 10)}.{rng.randrange(0, 10**16):016d}"
    ).encode("ascii")
    exponent_marker = b"e" if rng.randrange(2) else b"E"
    exponent = rng.randrange(-400, 308)
    exponent_text = f"{exponent:+d}".encode("ascii")
    return sign + coefficient + exponent_marker + exponent_text


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


def _random_key_token(rng: random.Random, index: int) -> bytes:
    generated_key = _random_string_token(rng)
    return b'"k' + str(index).encode("ascii") + b":" + generated_key[1:]


def _pad_generated_value(rng: random.Random, value: bytes) -> bytes:
    whitespace = (b"", b" ", b"\t", b"\r", b"\n", b" \t\r\n")
    return rng.choice(whitespace) + value + rng.choice(whitespace)


def _render_container(
    rng: random.Random,
    values: list[bytes],
) -> bytes:
    if rng.randrange(2) == 0:
        return b"[" + b",".join(values) + b"]"
    members = [
        _random_key_token(rng, index) + b":" + value
        for index, value in enumerate(values)
    ]
    return b"{" + b",".join(members) + b"}"


def _random_value(rng: random.Random, parent_depth: int) -> bytes:
    if parent_depth >= MAX_GENERATED_DEPTH or rng.randrange(4) != 0:
        value = _random_scalar(rng)
    else:
        width = rng.randrange(0, 4)
        values = [_random_value(rng, parent_depth + 1) for _ in range(width)]
        value = _render_container(rng, values)
    return _pad_generated_value(rng, value)


def _random_spine_container(
    rng: random.Random,
    depth: int,
    target_depth: int,
) -> bytes:
    if not 2 <= depth <= target_depth <= MAX_GENERATED_DEPTH:
        raise AssertionError("invalid generated depth spine")
    width = rng.randrange(1, 4) if depth < target_depth else rng.randrange(0, 4)
    spine_index = rng.randrange(width) if depth < target_depth else None
    values: list[bytes] = []
    for index in range(width):
        if index == spine_index:
            nested = _random_spine_container(rng, depth + 1, target_depth)
            values.append(_pad_generated_value(rng, nested))
        else:
            values.append(_random_value(rng, depth))
    return _render_container(rng, values)


def _random_document(rng: random.Random) -> bytes:
    target_depth = rng.randrange(1, MAX_GENERATED_DEPTH + 1)
    width = rng.randrange(1, MAX_GENERATED_WIDTH + 1)
    spine_index = rng.randrange(width) if target_depth > 1 else None
    values: list[bytes] = []
    for index in range(width):
        if index == spine_index:
            nested = _random_spine_container(rng, 2, target_depth)
            values.append(_pad_generated_value(rng, nested))
        else:
            values.append(_random_value(rng, 1))
    members = [
        _random_key_token(rng, index) + b":" + value
        for index, value in enumerate(values)
    ]
    return b"{" + b",".join(members) + b"}"


def _generate_valid_documents() -> list[bytes]:
    rng = random.Random(RNG_SEED)
    return [_random_document(rng) for _ in range(VALID_DOCUMENT_COUNT)]


def _first_root_key_token(raw: bytes) -> bytes:
    if not raw.startswith(b'{"'):
        raise AssertionError("generated mutation root must be a nonempty object")
    index = 2
    while index < len(raw):
        if raw[index] == 0x5C:
            index += 2
            continue
        if raw[index] == 0x22:
            return raw[1 : index + 1]
        index += 1
    raise AssertionError("generated root key is unterminated")


def _first_structural_colon(raw: bytes) -> int:
    in_string = False
    index = 0
    while index < len(raw):
        byte = raw[index]
        if in_string:
            if byte == 0x5C:
                index += 2
                continue
            if byte == 0x22:
                in_string = False
        elif byte == 0x22:
            in_string = True
        elif byte == 0x3A:
            return index
        index += 1
    raise AssertionError("generated root object has no structural colon")


def _mutate(family: str, base: bytes, index: int) -> bytes:
    if not base.endswith(b"}"):
        raise AssertionError("generated mutation base must be a root object")
    if family == "delimiter_deletion":
        return base[:-1]
    if family == "truncation":
        return base[: max(1, len(base) // 2)]
    if family == "trailing_comma":
        return base[:-1] + b",}"
    if family == "colon_comma_substitution":
        colon = _first_structural_colon(base)
        return base[:colon] + b"," + base[colon + 1 :]
    if family == "duplicate_key_insertion":
        key = _first_root_key_token(base)
        return base[:-1] + b"," + key + b":null}"
    if family == "invalid_escape":
        return base[:2] + b"\\x" + base[2:]
    if family == "malformed_exponent_or_leading_zero":
        malformed = b"01" if index % 2 else b"1e+"
        return base[:-1] + b',"mutation":' + malformed + b"}"
    if family == "extra_root_token":
        return base + b" null"
    if family == "invalid_or_truncated_utf8":
        invalid = b"\xff" if index % 2 else b"\xe2\x82"
        return base[:2] + invalid + base[2:]
    raise AssertionError(f"unknown mutation family: {family}")


def _mutations_for_document(
    base: bytes,
    document_index: int,
) -> tuple[tuple[str, bytes], ...]:
    first_family = (document_index * 3) % len(_MUTATION_FAMILIES)
    families = tuple(
        _MUTATION_FAMILIES[(first_family + offset) % len(_MUTATION_FAMILIES)]
        for offset in range(3)
    )
    return tuple(
        (family, _mutate(family, base, document_index))
        for family in families
    )


def test_valid_corpus_is_exactly_five_thousand_seeded_grammar_documents() -> None:
    expected_rng = random.Random(RNG_SEED)
    expected = [
        _random_document(expected_rng)
        for _ in range(VALID_DOCUMENT_COUNT)
    ]

    actual = _generate_valid_documents()

    assert len(actual) == VALID_DOCUMENT_COUNT
    assert actual == expected


def test_every_valid_document_has_exactly_three_actual_named_mutations() -> None:
    documents = _generate_valid_documents()
    mutation_counts: Counter[str] = Counter()
    total = 0

    for document_index, base in enumerate(documents):
        mutations = _mutations_for_document(base, document_index)
        assert len(mutations) == 3
        assert len({name for name, _ in mutations}) == 3
        for name, candidate in mutations:
            total += 1
            mutation_counts[name] += 1
            assert candidate != base
            oracle_accepted, _ = _strict_oracle(candidate)
            assert not oracle_accepted, (document_index, name, candidate[:256])
            if name == "delimiter_deletion":
                assert base.endswith(b"}")
                assert candidate == base[:-1]
            elif name == "truncation":
                assert len(candidate) < len(base)
                assert base.startswith(candidate)
            elif name == "trailing_comma":
                assert candidate == base[:-1] + b",}"
            elif name == "colon_comma_substitution":
                differences = [
                    index
                    for index, pair in enumerate(zip(base, candidate, strict=True))
                    if pair[0] != pair[1]
                ]
                assert len(differences) == 1
                difference = differences[0]
                assert base[difference] == ord(":")
                assert candidate[difference] == ord(",")
            elif name == "duplicate_key_insertion":
                assert candidate.startswith(base[:-1] + b",")
                assert candidate.endswith(b":null}")
            elif name == "invalid_escape":
                assert b"\\x" in candidate
                assert b"\\x" not in base
            elif name == "malformed_exponent_or_leading_zero":
                assert b':1e+}' in candidate or b':01}' in candidate
            elif name == "extra_root_token":
                assert candidate == base + b" null"
            elif name == "invalid_or_truncated_utf8":
                with pytest.raises(UnicodeDecodeError):
                    candidate.decode("utf-8", errors="strict")
            else:
                raise AssertionError(f"unknown mutation family: {name}")

    assert total == MUTATED_DOCUMENT_COUNT
    assert set(mutation_counts) == set(_MUTATION_FAMILIES)
    assert all(mutation_counts[name] > 0 for name in _MUTATION_FAMILIES)


def _json_number_tokens(raw: bytes) -> tuple[bytes, ...]:
    number_bytes = frozenset(b"0123456789+-.eE")
    tokens: list[bytes] = []
    in_string = False
    index = 0
    while index < len(raw):
        byte = raw[index]
        if in_string:
            if byte == 0x5C:
                index += 2
                continue
            if byte == 0x22:
                in_string = False
            index += 1
            continue
        if byte == 0x22:
            in_string = True
            index += 1
            continue
        if byte == 0x2D or 0x30 <= byte <= 0x39:
            end = index + 1
            while end < len(raw) and raw[end] in number_bytes:
                end += 1
            tokens.append(raw[index:end])
            index = end
            continue
        index += 1
    return tuple(tokens)


def test_fixed_seed_grammar_differential_matches_strict_duplicate_aware_oracle() -> None:
    valid_documents = _generate_valid_documents()
    assert len(valid_documents) == VALID_DOCUMENT_COUNT

    mutation_counts: Counter[str] = Counter()
    oracle_rejections: Counter[str] = Counter()
    mutated_documents: list[tuple[str, bytes]] = []
    for document_index, raw in enumerate(valid_documents):
        mutations = _mutations_for_document(raw, document_index)
        assert len(mutations) == 3
        for family, candidate in mutations:
            mutation_counts[family] += 1
            mutated_documents.append((family, candidate))

    assert len(mutated_documents) == MUTATED_DOCUMENT_COUNT
    assert set(mutation_counts) == set(_MUTATION_FAMILIES)
    assert sum(mutation_counts.values()) == MUTATED_DOCUMENT_COUNT

    cases = [("valid", raw) for raw in valid_documents] + mutated_documents
    assert len(cases) == VALID_DOCUMENT_COUNT + MUTATED_DOCUMENT_COUNT
    observed_valid_depth = 0
    observed_valid_width = 0
    observed_scalar_kinds: set[str] = set()
    observed_container_kinds: set[str] = set()
    observed_empty_containers: set[str] = set()
    observed_booleans: set[bool] = set()
    observed_empty_string = False
    observed_number_tokens: set[bytes] = set()
    observed_string_forms: set[bytes] = set()
    observed_whitespace: set[int] = set()
    maximum_valid_input_bytes = 0
    for case_index, (family, raw) in enumerate(cases):
        oracle_accepted, oracle_value = _strict_oracle(raw)
        if family == "valid":
            assert oracle_accepted, (case_index, raw[:256])
            depth, width = _oracle_shape(oracle_value)
            observed_valid_depth = max(observed_valid_depth, depth)
            observed_valid_width = max(observed_valid_width, width)
            maximum_valid_input_bytes = max(maximum_valid_input_bytes, len(raw))
            observed_number_tokens.update(_json_number_tokens(raw))
            observed_string_forms.update(
                form for form in _REQUIRED_GENERATED_STRING_FORMS if form in raw
            )
            observed_whitespace.update(byte for byte in raw if byte in b" \t\r\n")
            pending = [oracle_value]
            while pending:
                current = pending.pop()
                if current is None:
                    observed_scalar_kinds.add("null")
                elif type(current) is bool:
                    observed_scalar_kinds.add("boolean")
                    observed_booleans.add(current)
                elif type(current) is str:
                    observed_scalar_kinds.add("string")
                    observed_empty_string = observed_empty_string or current == ""
                elif type(current) in (int, float):
                    observed_scalar_kinds.add("number")
                elif type(current) is list:
                    observed_container_kinds.add("array")
                    if not current:
                        observed_empty_containers.add("array")
                    pending.extend(current)
                elif type(current) is dict:
                    observed_container_kinds.add("object")
                    if not current:
                        observed_empty_containers.add("object")
                    pending.extend(current.values())
                else:
                    raise AssertionError("oracle produced a non-JSON host value")
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
    assert observed_scalar_kinds == {"null", "boolean", "string", "number"}
    assert observed_booleans == {False, True}
    assert observed_empty_string
    assert observed_container_kinds == {"array", "object"}
    assert observed_empty_containers == {"array", "object"}
    assert observed_string_forms == set(_REQUIRED_GENERATED_STRING_FORMS)
    assert observed_whitespace == set(b" \t\r\n")
    assert _REQUIRED_GENERATED_NUMBER_TOKENS.issubset(observed_number_tokens)
    assert max(map(len, observed_number_tokens)) <= _limit(
        BudgetDimension.NUMBER_TOKEN_CHARS
    )
    assert maximum_valid_input_bytes <= _limit(BudgetDimension.RECIPE_INPUT_BYTES)
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
    assert "_generate_valid_documents" not in source
    assert "_random_document" not in source
