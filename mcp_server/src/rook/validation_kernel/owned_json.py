"""Transitively immutable, kernel-owned JSON values."""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeAlias, overload


class OwnedJsonError(ValueError):
    """Base class for rejected trusted JSON composition."""


class OwnedJsonTypeError(OwnedJsonError, TypeError):
    """A host value is not one of the exact supported JSON built-ins."""


class OwnedJsonValueError(OwnedJsonError):
    """A supported host value cannot be represented in the owned domain."""


class OwnedJsonAliasError(OwnedJsonValueError):
    """A host container is aliased or cyclic."""


class OwnedJsonDuplicateKeyError(OwnedJsonValueError):
    """An object member sequence contains a duplicate name."""


@dataclass(frozen=True, slots=True)
class JsonNull:
    """The JSON null value."""

    value: None = field(default=None, init=False)


@dataclass(frozen=True, slots=True)
class JsonBoolean:
    """An owned JSON boolean."""

    value: bool

    def __post_init__(self) -> None:
        if type(self.value) is not bool:
            raise OwnedJsonTypeError("JsonBoolean requires an exact bool")


@dataclass(frozen=True, slots=True)
class JsonString:
    """An owned Unicode string with no unpaired surrogates."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise OwnedJsonTypeError("JsonString requires an exact str")
        _validate_unicode_scalar_string(self.value)

    def __str__(self) -> str:
        return self.value


JsonNumberSource: TypeAlias = Literal[
    "integer", "fraction", "exponent", "trusted_float"
]
_JSON_NUMBER_SOURCES = frozenset(
    {"integer", "fraction", "exponent", "trusted_float"}
)


@dataclass(frozen=True, slots=True)
class JsonNumber:
    """One finite IEEE-754 binary64 value and its source classification."""

    value: float
    source_token_classification: JsonNumberSource = "trusted_float"

    def __post_init__(self) -> None:
        if type(self.value) is not float:
            raise OwnedJsonTypeError("JsonNumber requires an exact float")
        if not math.isfinite(self.value):
            raise OwnedJsonValueError("JsonNumber requires a finite binary64 value")
        if type(self.source_token_classification) is not str:
            raise OwnedJsonTypeError("number source classification requires an exact str")
        if self.source_token_classification not in _JSON_NUMBER_SOURCES:
            raise OwnedJsonValueError("unknown JSON number source classification")


@dataclass(frozen=True, slots=True)
class JsonArray(Sequence["JsonValue"]):
    """A tuple-backed owned JSON array."""

    items: tuple["JsonValue", ...]

    def __post_init__(self) -> None:
        if type(self.items) is not tuple:
            raise OwnedJsonTypeError("JsonArray storage must be an exact tuple")
        if any(not _is_json_value(item) for item in self.items):
            raise OwnedJsonTypeError("JsonArray items must be exact owned JSON values")

    @overload
    def __getitem__(self, index: int) -> "JsonValue": ...

    @overload
    def __getitem__(self, index: slice) -> tuple["JsonValue", ...]: ...

    def __getitem__(
        self, index: int | slice
    ) -> "JsonValue" | tuple["JsonValue", ...]:
        return self.items[index]

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator["JsonValue"]:
        return iter(self.items)


@dataclass(frozen=True, slots=True, init=False)
class JsonObject(Mapping[str, "JsonValue"]):
    """A UTF-16-key-sorted, tuple-backed owned JSON object."""

    members: tuple[tuple[JsonString, "JsonValue"], ...]
    _lookup_keys: tuple[bytes, ...] = field(repr=False)

    def __init__(
        self, members: tuple[tuple[JsonString, "JsonValue"], ...]
    ) -> None:
        sorted_members, lookup_keys = _prepare_object_members(members)
        object.__setattr__(self, "members", sorted_members)
        object.__setattr__(self, "_lookup_keys", lookup_keys)

    def __getitem__(self, key: str) -> "JsonValue":
        if type(key) is not str:
            raise KeyError(key)
        try:
            lookup_key = _utf16_sort_key(key)
        except OwnedJsonValueError:
            raise KeyError(key) from None
        index = bisect_left(self._lookup_keys, lookup_key)
        if index == len(self._lookup_keys) or self._lookup_keys[index] != lookup_key:
            raise KeyError(key)
        member_key, member_value = self.members[index]
        if member_key.value != key:
            raise KeyError(key)
        return member_value

    def __iter__(self) -> Iterator[str]:
        return (key.value for key, _ in self.members)

    def __len__(self) -> int:
        return len(self.members)


JsonValue: TypeAlias = (
    JsonNull | JsonBoolean | JsonString | JsonNumber | JsonArray | JsonObject
)
_JSON_VALUE_TYPES = (
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
)


def _validate_unicode_scalar_string(value: str) -> None:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise OwnedJsonValueError("JSON strings cannot contain unpaired surrogates") from None


def _utf16_sort_key(value: str) -> bytes:
    _validate_unicode_scalar_string(value)
    return value.encode("utf-16-be", errors="strict")


def _is_json_value(value: object) -> bool:
    return type(value) in _JSON_VALUE_TYPES


def _prepare_object_members(
    members: tuple[tuple[JsonString, JsonValue], ...],
) -> tuple[
    tuple[tuple[JsonString, JsonValue], ...],
    tuple[bytes, ...],
]:
    if type(members) is not tuple:
        raise OwnedJsonTypeError("JsonObject storage must be an exact tuple")

    prepared: list[tuple[bytes, JsonString, JsonValue]] = []
    names: set[str] = set()
    for member in members:
        if type(member) is not tuple or len(member) != 2:
            raise OwnedJsonTypeError("each JsonObject member must be an exact pair tuple")
        key, value = member
        if type(key) is not JsonString or not _is_json_value(value):
            raise OwnedJsonTypeError("JsonObject members require owned keys and values")
        if key.value in names:
            raise OwnedJsonDuplicateKeyError(f"duplicate JSON object member: {key.value!r}")
        names.add(key.value)
        prepared.append((_utf16_sort_key(key.value), key, value))

    prepared.sort(key=lambda item: item[0])
    sorted_members = tuple((key, value) for _, key, value in prepared)
    lookup_keys = tuple(sort_key for sort_key, _, _ in prepared)
    return sorted_members, lookup_keys


def _seal_object_members(
    members: tuple[tuple[JsonString, JsonValue], ...],
) -> JsonObject:
    """Seal parser-produced object pairs after duplicate detection and sorting."""

    return JsonObject(members)


def _convert_scalar(value: object) -> JsonValue:
    value_type = type(value)
    if value is None:
        return JsonNull()
    if value_type is bool:
        return JsonBoolean(value)
    if value_type is str:
        return JsonString(value)
    if value_type is int:
        try:
            binary64 = float(value)
        except OverflowError:
            raise OwnedJsonValueError("integer is outside the finite binary64 domain") from None
        if not math.isfinite(binary64):
            raise OwnedJsonValueError("integer is outside the finite binary64 domain")
        return JsonNumber(binary64, "integer")
    if value_type is float:
        if not math.isfinite(value):
            raise OwnedJsonValueError("trusted JSON numbers must be finite")
        return JsonNumber(value, "trusted_float")
    raise OwnedJsonTypeError(
        f"unsupported trusted JSON host type: {value_type.__name__}"
    )


def _take_results(results: list[JsonValue], count: int) -> tuple[JsonValue, ...]:
    if count == 0:
        return ()
    values = tuple(results[-count:])
    del results[-count:]
    return values


def own_trusted_json(value: object) -> JsonValue:
    """Copy an exact built-in JSON graph into immutable owned values."""

    results: list[JsonValue] = []
    seen_containers: set[int] = set()
    stack: list[tuple[str, object]] = [("visit", value)]

    while stack:
        operation, current = stack.pop()
        if operation == "finish_array":
            results.append(JsonArray(_take_results(results, int(current))))
            continue
        if operation == "finish_object":
            keys = current
            if type(keys) is not tuple:
                raise AssertionError("invalid trusted object conversion frame")
            child_values = _take_results(results, len(keys))
            members = tuple(zip(keys, child_values, strict=True))
            results.append(_seal_object_members(members))
            continue

        current_type = type(current)
        if current_type in (dict, list, tuple):
            identity = id(current)
            if identity in seen_containers:
                raise OwnedJsonAliasError(
                    "trusted JSON containers cannot be aliased or cyclic"
                )
            seen_containers.add(identity)

            if current_type is dict:
                try:
                    items = tuple(current.items())
                except RuntimeError:
                    raise OwnedJsonValueError("trusted JSON object changed during conversion") from None
                keys: list[JsonString] = []
                child_values: list[object] = []
                for key, child_value in items:
                    if type(key) is not str:
                        raise OwnedJsonTypeError("JSON object keys must be exact strings")
                    keys.append(JsonString(key))
                    child_values.append(child_value)
                stack.append(("finish_object", tuple(keys)))
            else:
                child_values = list(current)
                stack.append(("finish_array", len(child_values)))

            for child_value in reversed(child_values):
                stack.append(("visit", child_value))
            continue

        results.append(_convert_scalar(current))

    if len(results) != 1:
        raise AssertionError("trusted JSON conversion produced an invalid result stack")
    return results[0]


def count_json_nodes(root: JsonValue) -> int:
    """Count value nodes without recursion; object keys are not nodes."""

    if not _is_json_value(root):
        raise OwnedJsonTypeError("node counting requires an exact owned JSON value")

    count = 0
    stack = [root]
    while stack:
        current = stack.pop()
        count += 1
        if type(current) is JsonArray:
            stack.extend(current.items)
        elif type(current) is JsonObject:
            stack.extend(value for _, value in current.members)
    return count


def _decode_pointer_token(token: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 == len(token) or token[index + 1] not in ("0", "1"):
            raise ValueError("invalid RFC 6901 escape")
        decoded.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def lookup_json_pointer(root: JsonValue, pointer: str) -> JsonValue:
    """Resolve an RFC 6901 JSON Pointer against an owned value."""

    if not _is_json_value(root):
        raise OwnedJsonTypeError("JSON Pointer lookup requires an owned root")
    if type(pointer) is not str:
        raise TypeError("JSON Pointer must be an exact str")
    if pointer == "":
        return root
    if not pointer.startswith("/"):
        raise ValueError("a non-empty JSON Pointer must start with '/'")

    current = root
    for encoded_token in pointer[1:].split("/"):
        token = _decode_pointer_token(encoded_token)
        if type(current) is JsonObject:
            try:
                current = current[token]
            except KeyError:
                raise KeyError(pointer) from None
            continue
        if type(current) is JsonArray:
            if (
                not token
                or (token != "0" and token.startswith("0"))
                or not token.isascii()
                or not token.isdecimal()
            ):
                raise KeyError(pointer)
            if not current:
                raise KeyError(pointer)
            largest_index = str(len(current) - 1)
            if len(token) > len(largest_index) or (
                len(token) == len(largest_index) and token > largest_index
            ):
                raise KeyError(pointer)
            index = int(token)
            current = current[index]
            continue
        raise KeyError(pointer)
    return current


__all__ = (
    "JsonArray",
    "JsonBoolean",
    "JsonNull",
    "JsonNumber",
    "JsonNumberSource",
    "JsonObject",
    "JsonString",
    "JsonValue",
    "OwnedJsonAliasError",
    "OwnedJsonDuplicateKeyError",
    "OwnedJsonError",
    "OwnedJsonTypeError",
    "OwnedJsonValueError",
    "count_json_nodes",
    "lookup_json_pointer",
    "own_trusted_json",
)
