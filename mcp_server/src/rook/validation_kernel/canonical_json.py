"""Exact RFC 8785 canonicalization for kernel-owned JSON values."""

from __future__ import annotations

import hashlib
from typing import Protocol

from .owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    JsonValue,
    _utf16_sort_key,
)


_STRING_CHUNK_BYTES = 8_192
_OWNED_TYPES = (
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
)


class CanonicalJsonError(ValueError):
    """Base class for canonical JSON failures."""


class CanonicalJsonTypeError(CanonicalJsonError, TypeError):
    """An argument is not an exact supported canonicalization type."""


class CanonicalJsonSizeError(CanonicalJsonError):
    """Canonical output exceeded an inclusive byte limit."""

    def __init__(self, limit: int, observed_lower_bound: int) -> None:
        super().__init__(
            f"canonical JSON exceeds {limit} bytes "
            f"(observed at least {observed_lower_bound})"
        )
        self.limit = limit
        self.observed_lower_bound = observed_lower_bound


class CanonicalByteSink(Protocol):
    """Receives canonical UTF-8 chunks in order."""

    def write(self, chunk: bytes) -> None: ...


class _BoundedBufferSink:
    __slots__ = ("_buffer", "_limit")

    def __init__(self, limit: int | None) -> None:
        self._buffer = bytearray()
        self._limit = limit

    def write(self, chunk: bytes) -> None:
        observed = len(self._buffer) + len(chunk)
        if self._limit is not None and observed > self._limit:
            raise CanonicalJsonSizeError(self._limit, observed)
        self._buffer.extend(chunk)

    def finish(self) -> bytes:
        return bytes(self._buffer)


class _HashSink:
    __slots__ = ("_hash",)

    def __init__(self) -> None:
        self._hash = hashlib.sha256()

    def write(self, chunk: bytes) -> None:
        self._hash.update(chunk)

    def fingerprint(self) -> str:
        return f"sha256:{self._hash.hexdigest()}"


def utf16_sort_key(value: str) -> bytes:
    """Return unsigned big-endian UTF-16 code units with no BOM."""

    if type(value) is not str:
        raise CanonicalJsonTypeError("UTF-16 sorting requires an exact str")
    return _utf16_sort_key(value)


def _format_ecmascript_number(value: float) -> str:
    if value == 0.0:
        return "0"

    sign = "-" if value < 0.0 else ""
    # CPython supplies the shortest round-tripping digits; JCS pins how they
    # are arranged around the decimal point and exponent thresholds.
    shortest = repr(abs(value)).lower()
    if "e" in shortest:
        mantissa, exponent_text = shortest.split("e")
        exponent = int(exponent_text)
    else:
        mantissa = shortest
        exponent = 0

    if "." in mantissa:
        integer, fraction = mantissa.split(".")
    else:
        integer, fraction = mantissa, ""

    digits = integer + fraction
    decimal_point = len(integer) + exponent
    leading_zeroes = len(digits) - len(digits.lstrip("0"))
    digits = digits[leading_zeroes:].rstrip("0")
    decimal_point -= leading_zeroes
    if not digits:
        return "0"

    digit_count = len(digits)
    if digit_count <= decimal_point <= 21:
        body = digits + "0" * (decimal_point - digit_count)
    elif 0 < decimal_point <= 21:
        body = digits[:decimal_point] + "." + digits[decimal_point:]
    elif -6 < decimal_point <= 0:
        body = "0." + "0" * (-decimal_point) + digits
    else:
        output_exponent = decimal_point - 1
        coefficient = (
            digits if digit_count == 1 else digits[0] + "." + digits[1:]
        )
        exponent_sign = "+" if output_exponent >= 0 else ""
        body = f"{coefficient}e{exponent_sign}{output_exponent}"
    return sign + body


def _write_string(value: str, sink: CanonicalByteSink) -> None:
    buffer = bytearray(b'"')

    def append(piece: bytes) -> None:
        if len(buffer) + len(piece) > _STRING_CHUNK_BYTES:
            sink.write(bytes(buffer))
            buffer.clear()
        buffer.extend(piece)

    for character in value:
        code_point = ord(character)
        if code_point == 0x22:
            piece = b'\\"'
        elif code_point == 0x5C:
            piece = b"\\\\"
        elif code_point == 0x08:
            piece = b"\\b"
        elif code_point == 0x09:
            piece = b"\\t"
        elif code_point == 0x0A:
            piece = b"\\n"
        elif code_point == 0x0C:
            piece = b"\\f"
        elif code_point == 0x0D:
            piece = b"\\r"
        elif code_point <= 0x1F:
            piece = f"\\u{code_point:04x}".encode("ascii")
        else:
            piece = character.encode("utf-8", errors="strict")
        append(piece)
    append(b'"')
    if buffer:
        sink.write(bytes(buffer))


def write_canonical_json(value: JsonValue, sink: CanonicalByteSink) -> None:
    """Write canonical JSON iteratively in bounded chunks."""

    if type(value) not in _OWNED_TYPES:
        raise CanonicalJsonTypeError("canonicalization requires an exact owned JSON value")
    if not callable(getattr(sink, "write", None)):
        raise CanonicalJsonTypeError("canonical byte sink must provide write(bytes)")

    stack: list[JsonValue | bytes] = [value]
    while stack:
        current = stack.pop()
        if type(current) is bytes:
            sink.write(current)
        elif type(current) is JsonNull:
            sink.write(b"null")
        elif type(current) is JsonBoolean:
            sink.write(b"true" if current.value else b"false")
        elif type(current) is JsonString:
            _write_string(current.value, sink)
        elif type(current) is JsonNumber:
            sink.write(_format_ecmascript_number(current.value).encode("ascii"))
        elif type(current) is JsonArray:
            sink.write(b"[")
            stack.append(b"]")
            for index in range(len(current.items) - 1, -1, -1):
                stack.append(current.items[index])
                if index:
                    stack.append(b",")
        elif type(current) is JsonObject:
            sink.write(b"{")
            stack.append(b"}")
            for index in range(len(current.members) - 1, -1, -1):
                key, member_value = current.members[index]
                stack.append(member_value)
                stack.append(b":")
                stack.append(key)
                if index:
                    stack.append(b",")
        else:
            raise CanonicalJsonTypeError("owned JSON graph contains an unknown value type")


def canonical_json_bytes(
    value: JsonValue, *, max_bytes: int | None = None
) -> bytes:
    """Return exact canonical UTF-8, stopping before an over-limit append."""

    if max_bytes is not None:
        if type(max_bytes) is not int:
            raise CanonicalJsonTypeError("max_bytes must be an exact int or None")
        if max_bytes < 0:
            raise ValueError("max_bytes cannot be negative")
    sink = _BoundedBufferSink(max_bytes)
    write_canonical_json(value, sink)
    return sink.finish()


def canonical_fingerprint(value: JsonValue) -> str:
    """Hash canonical JSON without first materializing its complete byte string."""

    sink = _HashSink()
    write_canonical_json(value, sink)
    return sink.fingerprint()


def sha256_prefixed(data: bytes) -> str:
    """Return a lowercase, algorithm-prefixed SHA-256 digest."""

    if type(data) is not bytes:
        raise CanonicalJsonTypeError("SHA-256 input must be exact bytes")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def normalized_source_fingerprint(source_bytes: bytes) -> str:
    """Hash strict UTF-8 source after CRLF/CR-to-LF normalization."""

    if type(source_bytes) is not bytes:
        raise CanonicalJsonTypeError("source input must be exact bytes")
    source = source_bytes.decode("utf-8", errors="strict")
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return sha256_prefixed(normalized.encode("utf-8"))


__all__ = (
    "CanonicalByteSink",
    "CanonicalJsonError",
    "CanonicalJsonSizeError",
    "CanonicalJsonTypeError",
    "canonical_fingerprint",
    "canonical_json_bytes",
    "normalized_source_fingerprint",
    "sha256_prefixed",
    "utf16_sort_key",
    "write_canonical_json",
)
