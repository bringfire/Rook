from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path

import pytest

from rook.validation_kernel.canonical_json import (
    CanonicalJsonSizeError,
    CanonicalJsonTypeError,
    canonical_fingerprint,
    canonical_json_bytes,
    normalized_source_fingerprint,
    sha256_prefixed,
    utf16_sort_key,
    write_canonical_json,
)
from rook.validation_kernel.owned_json import (
    JsonNumber,
    OwnedJsonValueError,
    own_trusted_json,
)


FIXTURES = Path(__file__).parent / "fixtures" / "validation_kernel"
REQUIRED_DIRECTED_BITS = {
    "signed_zero": {"0000000000000000", "8000000000000000"},
    "decimal_fixed_transition": {
        "3eb0c6f7a0b5ed8c",
        "3eb0c6f7a0b5ed8d",
        "3eb0c6f7a0b5ed8e",
    },
    "large_fixed_transition": {
        "444b1ae4d6e2ef4f",
        "444b1ae4d6e2ef50",
        "444b1ae4d6e2ef51",
    },
    "integer_precision_transition": {
        "433fffffffffffff",
        "4340000000000000",
        "4340000000000001",
    },
    "minimum_subnormal": {
        "0000000000000000",
        "0000000000000001",
        "0000000000000002",
    },
    "normal_boundary": {
        "000ffffffffffffe",
        "000fffffffffffff",
        "0010000000000000",
        "0010000000000001",
    },
    "maximum_finite": {
        "7feffffffffffffe",
        "7fefffffffffffff",
    },
    "rfc8785_halfway": {
        "41b3de4355555553",
        "41b3de4355555554",
        "41b3de4355555555",
        "41b3de4355555556",
        "41b3de4355555557",
        "43143ff3c1cb0959",
    },
    "rfc8785_appendix_b": {
        "444b1ae4d6e2ef4e",
    },
}
REQUIRED_DIRECTED_RELATIONS = {
    "signed_zero": {"positive_zero", "negative_zero"},
    "decimal_fixed_transition": {"next_down", "center", "next_up"},
    "large_fixed_transition": {"next_down", "center", "next_up"},
    "integer_precision_transition": {"next_down", "center", "next_up"},
    "minimum_subnormal": {"next_down", "center", "next_up"},
    "normal_boundary": {
        "max_subnormal_next_down",
        "max_subnormal",
        "min_normal",
        "min_normal_next_up",
    },
    "maximum_finite": {"next_down", "center"},
    "rfc8785_halfway": {"appendix_b"},
    "rfc8785_appendix_b": {"appendix_b"},
}


def _float_from_bits(bits: str) -> float:
    return struct.unpack(">d", bytes.fromhex(bits))[0]


def test_checked_in_jcs_vectors_match_exact_ecmascript_spelling() -> None:
    vectors = json.loads((FIXTURES / "jcs_vectors.json").read_text(encoding="utf-8"))

    assert {
        "negative_zero",
        "fraction",
        "small_decimal",
        "small_exponent",
        "large_exponent",
        "rounded_binary64",
        "schema_integer_above_product_safe_range",
    }.issubset({vector["name"] for vector in vectors})
    for vector in vectors:
        value = own_trusted_json(float(vector["input"]))
        assert canonical_json_bytes(value).decode("ascii") == vector["canonical"], vector


def test_number_corpus_has_required_directed_groups_and_exact_spellings() -> None:
    rows = [
        json.loads(line)
        for line in (FIXTURES / "jcs_number_vectors.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert len(rows) == 20_000
    assert len({row["case_id"] for row in rows}) == len(rows)
    by_group: dict[str, set[str]] = {}
    relations_by_group: dict[str, set[str]] = {}
    for row in rows:
        assert re.fullmatch(r"[0-9a-f]{16}", row["bits"])
        assert row["case_id"]
        assert row["relation"]
        by_group.setdefault(row["group"], set()).add(row["bits"])
        relations_by_group.setdefault(row["group"], set()).add(row["relation"])

    for group, required_bits in REQUIRED_DIRECTED_BITS.items():
        assert required_bits.issubset(by_group[group]), group
    for group, required_relations in REQUIRED_DIRECTED_RELATIONS.items():
        assert required_relations.issubset(relations_by_group[group]), group

    for row in rows:
        value = _float_from_bits(row["bits"])
        assert math.isfinite(value), row
        actual = canonical_json_bytes(own_trusted_json(value)).decode("ascii")
        assert actual == row["canonical"], row


def test_utf16_object_key_order_matches_rfc_8785_example() -> None:
    value = own_trusted_json(
        {
            "\u20ac": "Euro Sign",
            "\r": "Carriage Return",
            "\ufb33": "Hebrew Letter Dalet With Dagesh",
            "1": "One",
            "\U0001f600": "Emoji: Grinning Face",
            "\u0080": "Control",
            "\u00f6": "Latin Small Letter O With Diaeresis",
        }
    )

    expected = (
        '{"\\r":"Carriage Return","1":"One","\u0080":"Control",'
        '"\u00f6":"Latin Small Letter O With Diaeresis",'
        '"\u20ac":"Euro Sign","\U0001f600":"Emoji: Grinning Face",'
        '"\ufb33":"Hebrew Letter Dalet With Dagesh"}'
    ).encode("utf-8")
    assert canonical_json_bytes(value) == expected


def test_utf16_sort_key_uses_big_endian_code_units_without_a_bom() -> None:
    assert utf16_sort_key("a") == b"\x00a"
    assert utf16_sort_key("\U0001f600") == bytes.fromhex("d83dde00")
    assert utf16_sort_key("\U0001f600") < utf16_sort_key("\ue000")
    with pytest.raises(OwnedJsonValueError):
        utf16_sort_key("\ud800")


def test_strings_use_exact_json_control_escaping_and_preserve_slash() -> None:
    value = own_trusted_json("\x00\b\t\n\f\r\x0f\"\\/")

    assert canonical_json_bytes(value) == b'"\\u0000\\b\\t\\n\\f\\r\\u000f\\"\\\\/"'


def test_output_is_utf8_without_bom_and_without_unicode_normalization() -> None:
    composed = own_trusted_json("\u00e9")
    decomposed = own_trusted_json("e\u0301")

    assert canonical_json_bytes(own_trusted_json("\u20ac")) == b'"\xe2\x82\xac"'
    assert not canonical_json_bytes(composed).startswith(b"\xef\xbb\xbf")
    assert canonical_json_bytes(composed) != canonical_json_bytes(decomposed)
    assert canonical_fingerprint(composed) != canonical_fingerprint(decomposed)


def test_integer_and_float_host_forms_share_the_binary64_spelling() -> None:
    assert canonical_json_bytes(own_trusted_json(42)) == b"42"
    assert canonical_json_bytes(own_trusted_json(42.0)) == b"42"
    assert canonical_json_bytes(own_trusted_json(9_007_199_254_740_992)) == (
        b"9007199254740992"
    )


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_cannot_enter_canonicalization(number: float) -> None:
    with pytest.raises(OwnedJsonValueError):
        JsonNumber(number)


def test_serializer_is_iterative_for_deep_values() -> None:
    host: object = 0
    for _ in range(2_500):
        host = [host]

    assert canonical_json_bytes(own_trusted_json(host)) == (
        b"[" * 2_500 + b"0" + b"]" * 2_500
    )


def test_streaming_serializer_writes_bounded_chunks() -> None:
    class RecordingSink:
        def __init__(self) -> None:
            self.chunks: list[bytes] = []

        def write(self, chunk: bytes) -> None:
            self.chunks.append(chunk)

    sink = RecordingSink()
    value = own_trusted_json({"payload": "x" * 100_000})

    write_canonical_json(value, sink)

    assert b"".join(sink.chunks) == canonical_json_bytes(value)
    assert sink.chunks
    assert max(map(len, sink.chunks)) <= 8_192


def test_canonical_byte_limit_is_inclusive_and_checked_before_append() -> None:
    value = own_trusted_json({"a": "b"})
    expected = b'{"a":"b"}'

    assert canonical_json_bytes(value, max_bytes=len(expected)) == expected
    with pytest.raises(CanonicalJsonSizeError) as error:
        canonical_json_bytes(value, max_bytes=len(expected) - 1)
    assert error.value.limit == len(expected) - 1
    assert error.value.observed_lower_bound == len(expected)


@pytest.mark.parametrize("max_bytes", [-1, True, 1.5])
def test_canonical_byte_limit_requires_a_nonnegative_exact_integer(
    max_bytes: object,
) -> None:
    with pytest.raises((CanonicalJsonTypeError, ValueError)):
        canonical_json_bytes(own_trusted_json(None), max_bytes=max_bytes)


def test_canonicalizer_accepts_only_exact_owned_values() -> None:
    with pytest.raises(CanonicalJsonTypeError):
        canonical_json_bytes({"not": "owned"})


def test_fingerprints_are_lowercase_prefixed_sha256() -> None:
    value = own_trusted_json({"b": 2, "a": 1})
    reordered = own_trusted_json({"a": 1, "b": 2})
    canonical = b'{"a":1,"b":2}'
    expected = f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    assert sha256_prefixed(b"abc") == (
        "sha256:ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
    assert canonical_fingerprint(value) == expected
    assert canonical_fingerprint(reordered) == expected
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", expected)


def test_source_fingerprint_validates_utf8_and_normalizes_line_endings() -> None:
    expected = sha256_prefixed(b"first\nsecond\nthird\n")

    assert normalized_source_fingerprint(b"first\r\nsecond\rthird\n") == expected
    with pytest.raises(CanonicalJsonTypeError):
        normalized_source_fingerprint(bytearray(b"source"))
    with pytest.raises(UnicodeDecodeError):
        normalized_source_fingerprint(b"\xff")
