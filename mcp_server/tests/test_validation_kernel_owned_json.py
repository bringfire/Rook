from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest

from rook.validation_kernel.owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    OwnedJsonAliasError,
    OwnedJsonDuplicateKeyError,
    OwnedJsonTypeError,
    OwnedJsonValueError,
    _seal_object_members,
    count_json_nodes,
    lookup_json_pointer,
    own_trusted_json,
)


def test_trusted_conversion_accepts_only_exact_json_builtins() -> None:
    value = own_trusted_json(
        {
            "null": None,
            "boolean": True,
            "string": "text",
            "integer": 7,
            "float": 1.5,
            "list": [False],
            "tuple": ("item",),
        }
    )

    assert isinstance(value, JsonObject)
    assert isinstance(value["null"], JsonNull)
    assert isinstance(value["boolean"], JsonBoolean)
    assert isinstance(value["string"], JsonString)
    assert isinstance(value["integer"], JsonNumber)
    assert isinstance(value["float"], JsonNumber)
    assert isinstance(value["list"], JsonArray)
    assert isinstance(value["tuple"], JsonArray)
    assert value["null"].value is None
    assert value["boolean"].value is True
    assert value["string"].value == "text"
    assert value["integer"].value == 7.0
    assert value["float"].value == 1.5


def test_numbers_retain_closed_source_classification() -> None:
    integer = own_trusted_json(1)
    trusted_float = own_trusted_json(1.0)

    assert isinstance(integer, JsonNumber)
    assert isinstance(trusted_float, JsonNumber)
    assert integer.source_token_classification == "integer"
    assert trusted_float.source_token_classification == "trusted_float"
    assert JsonNumber(1.5, "fraction").source_token_classification == "fraction"
    assert JsonNumber(1e30, "exponent").source_token_classification == "exponent"
    with pytest.raises(OwnedJsonValueError):
        JsonNumber(1.0, "unknown")
    with pytest.raises(OwnedJsonTypeError):
        JsonNumber(1.0, type("TokenSubclass", (str,), {})("fraction"))


def test_trusted_conversion_rejects_non_json_host_scalars() -> None:
    for value in (Decimal("1"), b"x", bytearray(b"x"), {1, 2}, complex(1, 2)):
        with pytest.raises(OwnedJsonTypeError):
            own_trusted_json(value)


@pytest.mark.parametrize(
    "value",
    [
        type("DictSubclass", (dict,), {})(),
        type("ListSubclass", (list,), {})(),
        type("TupleSubclass", (tuple,), {})(),
        type("StringSubclass", (str,), {})("x"),
        type("IntSubclass", (int,), {})(1),
        type("FloatSubclass", (float,), {})(1.0),
    ],
)
def test_trusted_conversion_rejects_supported_type_subclasses(value: object) -> None:
    with pytest.raises(OwnedJsonTypeError):
        own_trusted_json(value)


def test_trusted_conversion_rejects_non_string_object_keys() -> None:
    with pytest.raises(OwnedJsonTypeError):
        own_trusted_json({1: "value"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_trusted_conversion_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(OwnedJsonValueError):
        own_trusted_json(value)


def test_trusted_conversion_rejects_integer_outside_binary64_domain() -> None:
    with pytest.raises(OwnedJsonValueError):
        own_trusted_json(10**10_000)


@pytest.mark.parametrize("value", ["\ud800", "\udfff", {"\ud800": "value"}])
def test_trusted_conversion_rejects_unpaired_surrogates(value: object) -> None:
    with pytest.raises(OwnedJsonValueError):
        own_trusted_json(value)


def test_trusted_conversion_rejects_container_aliases_and_cycles() -> None:
    shared: list[object] = []
    cycle: list[object] = []
    cycle.append(cycle)

    with pytest.raises(OwnedJsonAliasError):
        own_trusted_json([shared, shared])
    with pytest.raises(OwnedJsonAliasError):
        own_trusted_json(cycle)


def test_owned_tree_is_transitively_immutable() -> None:
    value = own_trusted_json({"a": [{"b": 1}]})

    assert isinstance(value, JsonObject)
    assert isinstance(value["a"], JsonArray)
    with pytest.raises(TypeError):
        value["a"][0]["b"] = 2
    with pytest.raises((AttributeError, TypeError)):
        value["a"].items = ()
    with pytest.raises((AttributeError, TypeError)):
        value.members = ()


def test_owned_containers_expose_only_immutable_storage() -> None:
    root = own_trusted_json({"a": [{"b": 1}]})
    pending = [root]

    while pending:
        current = pending.pop()
        assert not hasattr(current, "__dict__")
        for name in dir(current):
            if name.startswith("_"):
                continue
            attribute = getattr(current, name)
            if callable(attribute):
                continue
            assert not isinstance(attribute, (dict, list, set, bytearray))
        if isinstance(current, JsonObject):
            assert isinstance(current.members, tuple)
            pending.extend(member_value for _, member_value in current.members)
        elif isinstance(current, JsonArray):
            assert isinstance(current.items, tuple)
            pending.extend(current.items)


def test_object_and_array_implement_read_only_collection_interfaces() -> None:
    value = own_trusted_json({"array": [1, 2], "other": False})

    assert isinstance(value, Mapping)
    assert isinstance(value["array"], Sequence)
    assert list(value) == ["array", "other"]
    assert len(value) == 2
    assert [item.value for item in value["array"]] == [1.0, 2.0]
    assert value["array"][:] == value["array"].items
    with pytest.raises(TypeError):
        value["new"] = own_trusted_json(None)
    with pytest.raises(TypeError):
        value["array"][0] = own_trusted_json(3)


def test_object_members_use_utf16_code_unit_order() -> None:
    value = own_trusted_json({"\ue000": 1, "\U0001f600": 2, "a": 3})

    assert list(value) == ["a", "\U0001f600", "\ue000"]


def test_pair_oriented_object_seal_rejects_duplicate_member_names() -> None:
    key = JsonString("duplicate")

    with pytest.raises(OwnedJsonDuplicateKeyError):
        _seal_object_members(
            ((key, own_trusted_json(1)), (key, own_trusted_json(2)))
        )


def test_node_count_is_iterative_for_deep_owned_trees() -> None:
    host: object = None
    for _ in range(2_500):
        host = [host]

    value = own_trusted_json(host)

    assert count_json_nodes(value) == 2_501


def test_json_pointer_resolves_root_objects_arrays_and_escapes() -> None:
    root = own_trusted_json(
        {"": "empty", "a/b": {"~key": ["zero", {"value": 2}]}}
    )

    assert lookup_json_pointer(root, "") is root
    assert lookup_json_pointer(root, "/").value == "empty"
    assert lookup_json_pointer(root, "/a~1b/~0key/0").value == "zero"
    assert lookup_json_pointer(root, "/a~1b/~0key/1/value").value == 2.0


@pytest.mark.parametrize("pointer", ["not-a-pointer", "/bad~", "/bad~2escape"])
def test_json_pointer_rejects_invalid_syntax_and_escapes(pointer: str) -> None:
    with pytest.raises(ValueError):
        lookup_json_pointer(own_trusted_json({}), pointer)


@pytest.mark.parametrize(
    "pointer",
    ["/missing", "/array/2", "/array/01", "/array/-", "/array/x", "/scalar/x"],
)
def test_json_pointer_reports_missing_or_inapplicable_paths(pointer: str) -> None:
    root = own_trusted_json({"array": [0, 1], "scalar": True})

    with pytest.raises(KeyError):
        lookup_json_pointer(root, pointer)


def test_json_pointer_reports_overlong_array_index_as_not_found() -> None:
    root = own_trusted_json({"array": [0]})

    with pytest.raises(KeyError):
        lookup_json_pointer(root, "/array/" + "9" * 5_000)
