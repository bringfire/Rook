from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OBJECTS_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "ObjectsHandler.cpp"
OBJECTS_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "ObjectsHandler.h"
USER_TEXT_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "UserTextHandler.cpp"
USER_TEXT_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "UserTextHandler.h"
ROOK_SERVER_CPP = REPO_ROOT / "src" / "RookNative" / "RookServer.cpp"
ROOK_SERVER_H = REPO_ROOT / "src" / "RookNative" / "RookServer.h"


def _extract_braced_source(source: str, start: int, body_start: int, label: str) -> str:
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not find closing brace for {label}")


def _extract_function(source: str, signature: str) -> str:
    start = source.find(signature)
    if start == -1:
        raise AssertionError(f"Missing function signature: {signature!r}")

    body_start = source.find("{", start)
    declaration_end = source.find(";", start)
    if body_start == -1 or (declaration_end != -1 and declaration_end < body_start):
        raise AssertionError(f"Missing opening brace for function {signature!r}")

    return _extract_braced_source(source, start, body_start, f"function {signature!r}")


def _extract_named_function(source: str, name: str) -> str:
    pattern = re.compile(
        rf"(?m)^[^\S\r\n]*(?:[\w:<>,~*&]+\s+)+{re.escape(name)}\s*"
        r"\([^;{}]*\)\s*\{"
    )
    match = pattern.search(source)
    if not match:
        raise AssertionError(f"Missing function definition: {name!r}")

    body_start = source.find("{", match.start(), match.end())
    if body_start == -1:
        raise AssertionError(f"Missing opening brace for function {name!r}")

    return _extract_braced_source(
        source, match.start(), body_start, f"function {name!r}"
    )


def _extract_post_route_registration(source: str, route: str) -> str:
    match = re.search(rf'm_server->Post\(\s*"{re.escape(route)}"\s*,', source)
    if not match:
        raise AssertionError(f"Missing POST route registration for {route!r}")

    rest = source[match.end() :]
    next_route = re.search(r"\n\s*m_server->(?:Get|Post|Put|Delete|Patch)\s*\(", rest)
    end = match.end() + next_route.start() if next_route else len(source)
    return source[match.start() : end]


def _assert_post_route_delegates(source: str, route: str, handler_call: str) -> None:
    registration = _extract_post_route_registration(source, route)
    assert handler_call in registration, (
        f"POST route {route!r} does not delegate to {handler_call!r}"
    )


def _split_top_level_arguments(argument_source: str) -> list[str]:
    args: list[str] = []
    start = 0
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(argument_source):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        elif (
            char == ","
            and paren_depth == 0
            and bracket_depth == 0
            and brace_depth == 0
        ):
            args.append(argument_source[start:index].strip())
            start = index + 1

    args.append(argument_source[start:].strip())
    return args


def _extract_call_arguments(source: str, call_start: int) -> list[str]:
    open_paren = source.find("(", call_start)
    if open_paren == -1:
        raise AssertionError("Missing opening parenthesis for call")

    depth = 0
    in_string = False
    escaped = False
    for index in range(open_paren, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return _split_top_level_arguments(source[open_paren + 1 : index])

    raise AssertionError("Missing closing parenthesis for call")


def _iter_variable_assignments(body: str):
    return re.finditer(
        r"\b(?:const\s+)?(?:auto|std::string|ON_wString|ON_UUID|UUID|"
        r"nlohmann::json|json|[\w:<>]+)"
        r"\s*(?:[&*]\s*)?(\w+)\s*=\s*([^;]+);",
        body,
        re.DOTALL,
    )


def _outer_parentheses_wrap_expression(expression: str) -> bool:
    expression = expression.strip()
    if not expression.startswith("(") or not expression.endswith(")"):
        return False

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(expression):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(expression) - 1:
                return False

    return depth == 0


def _strip_transparent_wrappers(expression: str) -> str:
    current = expression.strip()
    while True:
        if _outer_parentheses_wrap_expression(current):
            current = current[1:-1].strip()
            continue

        if re.match(r"^std::move\s*\(", current):
            args = _extract_call_arguments(current, 0)
            if len(args) == 1:
                current = args[0].strip()
                continue

        return current


def _expression_matches_value_pattern(expression: str, value_pattern: str) -> bool:
    normalized = _strip_transparent_wrappers(expression)
    return bool(re.fullmatch(rf"\s*(?:{value_pattern})\s*", normalized, re.DOTALL))


def _normalize_expression_identity(expression: str) -> str:
    return re.sub(r"\s+", " ", _strip_transparent_wrappers(expression)).strip()


def _iter_json_key_value_occurrences(body: str, key: str) -> list[tuple[str, int, str, str]]:
    occurrences: list[tuple[str, int, str, str]] = []
    assignment_pattern = re.compile(
        rf"(?:(?P<target>\b[A-Za-z_]\w*(?:\s*(?:\.|->)\s*[A-Za-z_]\w*)*)\s*)?"
        rf"\[\s*\"{re.escape(key)}\"\s*\]\s*=\s*(?P<value>[^;]+);",
        re.DOTALL,
    )
    for match in assignment_pattern.finditer(body):
        occurrences.append(
            (
                match.group("value").strip(),
                match.start(),
                match.group("target") or "",
                "assignment",
            )
        )

    for pair in re.finditer(rf"\{{\s*\"{re.escape(key)}\"\s*,", body):
        try:
            pair_source = _extract_braced_source(
                body, pair.start(), pair.start(), f"{key} JSON pair"
            )
        except AssertionError:
            continue
        pair_args = _split_top_level_arguments(pair_source[1:-1])
        if len(pair_args) >= 2 and re.fullmatch(rf'"{re.escape(key)}"', pair_args[0]):
            occurrences.append((pair_args[1].strip(), pair.start(), "", "pair"))

    return occurrences


def _iter_json_key_values(body: str, key: str) -> list[str]:
    return [
        value
        for value, _position, _target, _kind in _iter_json_key_value_occurrences(
            body, key
        )
    ]


def _is_top_level_response_root(target: str) -> bool:
    normalized = re.sub(r"\s+", "", target)
    return normalized in {"wr.data", "data", "response", "payload"}


def _is_per_object_json_target(target: str) -> bool:
    normalized = re.sub(r"\s+", "", target)
    if not normalized or _is_top_level_response_root(normalized):
        return False
    final_name = re.split(r"(?:\.|->)", normalized)[-1]
    return bool(re.search(r"(?:item|result|entry|record|object)", final_name, re.I))


def _is_per_object_userstrings_pair_context(body: str, position: int) -> bool:
    prefix = body[max(0, position - 320) : position]
    return bool(
        re.search(
            r"(?:results|items|objects|objectResults)\s*(?:\.|->)\s*"
            r"(?:push_back|emplace_back|append)\s*\([\s\S]*$",
            prefix,
            re.IGNORECASE,
        )
        or re.search(
            r"\b(?:auto|nlohmann::json|json)\s+"
            r"\w*(?:item|result|entry|record|object)\w*\s*(?:=|\{)[\s\S]*$",
            prefix,
            re.IGNORECASE,
        )
        or re.search(
            r"\b\w*(?:item|result|entry|record|object)\w*\s*=\s*"
            r"(?:nlohmann::json|json)?\s*\{[\s\S]*$",
            prefix,
            re.IGNORECASE,
        )
    )


def _iter_per_object_userstrings_values(body: str) -> list[str]:
    values: list[str] = []
    for value, position, target, kind in _iter_json_key_value_occurrences(
        body, "userStrings"
    ):
        if kind == "assignment" and _is_per_object_json_target(target):
            values.append(value)
        elif kind == "pair" and _is_per_object_userstrings_pair_context(
            body, position
        ):
            values.append(value)
    return values


def _expression_uses_json_key(expression: str, key: str) -> bool:
    return bool(
        re.search(
            rf"(?:\[\s*\"{re.escape(key)}\"\s*\]"
            rf"|\.at\s*\(\s*\"{re.escape(key)}\"\s*\)"
            rf"|\.value\s*\(\s*\"{re.escape(key)}\"\s*,"
            rf"|\b(?:RequiredString|RequireString|ReadString|GetString|ParseString|"
            rf"JsonString|JsonRequiredString)\s*\([^;]*\"{re.escape(key)}\")",
            expression,
        )
    )


def _variable_assigned_from_json_key(body: str, variable: str, key: str) -> bool:
    for assignment in _iter_variable_assignments(body):
        if assignment.group(1) != variable:
            continue
        if _expression_uses_json_key(assignment.group(2), key):
            return True

    return False


def _assert_set_visible_attrs_are_modified(body: str) -> None:
    attributes_variables = set(
        re.findall(
            r"\b(?:const\s+)?(?:auto|ON_3dmObjectAttributes|CRhinoObjectAttributes|[\w:<>]+)"
            r"\s*(?:[&*]\s*)?(\w+)\s*(?:=\s*[^;]*\bAttributes\s*\(\s*\)"
            r"|\(\s*[^;]*\bAttributes\s*\(\s*\)\s*\))",
            body,
            re.DOTALL,
        )
    )
    assert attributes_variables, (
        "HandleObjectVisibility must copy object attributes before changing visibility"
    )

    for attributes_var in attributes_variables:
        if not re.search(
            rf"\b{re.escape(attributes_var)}\s*\.\s*SetVisible\s*\(\s*[^)]+\s*\)",
            body,
        ):
            continue
        for modify_call in re.finditer(r"\bModifyObjectAttributes\s*\(", body):
            args = _extract_call_arguments(body, modify_call.start())
            if any(
                re.search(rf"\b{re.escape(attributes_var)}\b", arg)
                for arg in args
            ):
                return

    raise AssertionError(
        "HandleObjectVisibility must pass the same attributes object changed by "
        "SetVisible(...) to ModifyObjectAttributes(...)"
    )


def _assert_set_layer_attrs_are_modified(body: str, target_layer_var: str) -> None:
    for layer_assignment in re.finditer(
        rf"\b(\w+)\s*\.\s*m_layer_index\s*=\s*"
        rf"{re.escape(target_layer_var)}\s*\.\s*index\b",
        body,
    ):
        attributes_var = layer_assignment.group(1)
        after_assignment = body[layer_assignment.end() :]
        for modify_call in re.finditer(r"\bModifyObjectAttributes\s*\(", after_assignment):
            args = _extract_call_arguments(after_assignment, modify_call.start())
            if any(
                re.search(rf"\b{re.escape(attributes_var)}\b", arg)
                for arg in args
            ):
                return

    raise AssertionError(
        "HandleObjectSetLayer must pass the same attributes object whose "
        "m_layer_index was changed to ModifyObjectAttributes(...)"
    )


def _extract_resolved_layer_variable(body: str) -> str:
    match = re.search(
        r"(?:const\s+)?(?:auto|[\w:<>]+)\s*(?:[&*]\s*)?(\w+)\s*=\s*"
        r"(?:[A-Za-z_]\w*::)*ResolveLayerRef\s*\(",
        body,
        re.DOTALL,
    )
    assert match, "HandleObjectSetLayer must resolve the target layer from the request"
    args = _extract_call_arguments(body, match.end() - 1)
    assert len(args) >= 3, "ResolveLayerRef must receive pDoc, layer value, and field name"
    assert re.fullmatch(r"(?:\w+\s*(?:->|\.)\s*)?pDoc", args[0]), (
        "ResolveLayerRef must use pDoc as the first argument"
    )
    assert re.fullmatch(r'"layer"', args[2]), (
        "ResolveLayerRef must label the request field as \"layer\""
    )

    layer_arg = args[1]
    layer_arg_vars = re.findall(r"\b[A-Za-z_]\w*\b", layer_arg)
    assert _expression_uses_json_key(layer_arg, "layer") or any(
        _variable_assigned_from_json_key(body, variable, "layer")
        for variable in layer_arg_vars
    ), "ResolveLayerRef must resolve the request body layer value"
    return match.group(1)


def _assert_parser_enforces_batch_cap(parser_body: str, constant_name: str) -> None:
    assert constant_name in parser_body
    size_call = (
        r"(?:[A-Za-z_]\w*(?:\s*->\s*\w+|\s*\.\s*\w+|\s*\[[^\]]+\])?"
        r"\s*\.\s*size\s*\(\s*\)|\bsize\s*\(\s*\))"
    )
    cap_value = rf"(?:{constant_name}|static_cast\s*<[^>]+>\s*\(\s*{constant_name}\s*\))"
    over_cap_comparison = (
        rf"(?:{size_call}\s*>\s*{cap_value}|{cap_value}\s*<\s*{size_call})"
    )
    assert re.search(over_cap_comparison, parser_body), (
        f"Parser must compare input size as over-cap against {constant_name}"
    )
    assert re.search(rf"if\s*\([\s\S]{{0,360}}{over_cap_comparison}[\s\S]{{0,360}}throw", parser_body), (
        f"Parser must reject batches over {constant_name}"
    )


def _extract_top_level_initializer_entries(initializer: str) -> list[str]:
    root_start = initializer.find("{")
    if root_start == -1:
        return []

    entries: list[str] = []
    depth = 0
    entry_start: int | None = None
    for index in range(root_start, len(initializer)):
        char = initializer[index]
        if char == "{":
            depth += 1
            if depth == 2:
                entry_start = index
        elif char == "}":
            if depth == 2 and entry_start is not None:
                entries.append(initializer[entry_start : index + 1])
                entry_start = None
            depth -= 1
            if depth == 0:
                break
    return entries


def _target_layer_metadata_aliases(
    body: str, target_layer_var: str
) -> tuple[set[str], set[str]]:
    path_aliases: set[str] = set()
    id_aliases: set[str] = set()

    for assignment in _iter_variable_assignments(body):
        variable = assignment.group(1)
        expression = assignment.group(2)
        if re.search(
            rf"\b{re.escape(target_layer_var)}\s*\.\s*(?:path|fullPath)\b",
            expression,
        ):
            path_aliases.add(variable)
        if re.search(rf"\b{re.escape(target_layer_var)}\s*\.\s*id\b", expression):
            id_aliases.add(variable)
        if (
            re.search(
                rf"\b{re.escape(target_layer_var)}\s*\.\s*index\b", expression
            )
            and re.search(
                r"(?:m_layer_table|LayerTable|\.Id\s*\(|LayerId|layerId|UuidToString)",
                expression,
            )
        ):
            id_aliases.add(variable)

    return id_aliases, path_aliases


def _metadata_source_uses_alias(
    metadata_source: str, key: str, aliases: set[str]
) -> bool:
    return any(
        _expression_matches_value_pattern(value, rf"\b{re.escape(alias)}\b")
        for value in _iter_json_key_values(metadata_source, key)
        for alias in aliases
    )


def _assert_set_layer_response_metadata(body: str, target_layer_var: str) -> None:
    response_root = r"(?:\bwr\s*\.\s*data|\bdata|\bresponse|\bpayload)"
    metadata_windows: list[str] = []
    id_aliases, path_aliases = _target_layer_metadata_aliases(
        body, target_layer_var
    )

    for assignment in re.finditer(
        rf"{response_root}\s*\[\s*\"layer\"\s*\]\s*=\s*([^;\n]+)", body
    ):
        assigned_expression = assignment.group(1).strip()
        windows = [body[assignment.start() : assignment.start() + 1200]]

        variable_match = re.match(r"([A-Za-z_]\w*)\b", assigned_expression)
        if variable_match:
            metadata_var = variable_match.group(1)
            variable_pattern = rf"\b{re.escape(metadata_var)}\s*\[\s*\"{{key}}\"\s*\]"
            for key in ("input", "index", "id", "path"):
                key_match = re.search(variable_pattern.format(key=key), body)
                if key_match:
                    windows.append(body[key_match.start() : key_match.start() + 240])

        metadata_windows.append("\n".join(windows))

    for assignment in re.finditer(
        rf"{response_root}\s*=\s*(?:nlohmann::json|json)?\s*\{{", body
    ):
        initializer_start = body.find("{", assignment.start(), assignment.end())
        initializer = _extract_braced_source(
            body,
            assignment.start(),
            initializer_start,
            "top-level response initializer",
        )
        for entry in _extract_top_level_initializer_entries(initializer):
            layer_pair = re.match(r"\{\s*\"layer\"\s*,", entry)
            if not layer_pair:
                continue
            value_fragment = entry[layer_pair.end() : layer_pair.end() + 240]
            value_fragment = value_fragment.lstrip()
            if not value_fragment.startswith("{"):
                windows = [entry]
                variable_match = re.match(r"([A-Za-z_]\w*)\b", value_fragment)
                if variable_match:
                    metadata_var = variable_match.group(1)
                    variable_pattern = (
                        rf"\b{re.escape(metadata_var)}\s*\[\s*\"{{key}}\"\s*\]"
                    )
                    for key in ("input", "index", "id", "path"):
                        key_match = re.search(variable_pattern.format(key=key), body)
                        if key_match:
                            windows.append(
                                body[key_match.start() : key_match.start() + 240]
                            )
                metadata_windows.append("\n".join(windows))
                continue
            layer_value_start = entry.find("{", layer_pair.end())
            try:
                metadata_windows.append(
                    _extract_braced_source(
                        entry,
                        layer_pair.start(),
                        layer_value_start,
                        "top-level layer metadata initializer",
                    )
                )
            except AssertionError:
                metadata_windows.append(entry)

    assert metadata_windows, (
        "HandleObjectSetLayer must emit top-level resolved layer metadata"
    )

    for metadata_source in metadata_windows:
        has_shape = all(
            re.search(rf"(?:\[\s*\"{key}\"\s*\]|\{{\s*\"{key}\"|,\s*\"{key}\")", metadata_source)
            for key in ("input", "index", "id", "path")
        )
        has_index = re.search(
            rf"\b{re.escape(target_layer_var)}\s*\.\s*index\b", metadata_source
        )
        has_id = re.search(
            rf"\b{re.escape(target_layer_var)}\s*\.\s*id\b", metadata_source
        ) or _metadata_source_uses_alias(
            metadata_source, "id", id_aliases
        ) or re.search(
            rf"(?:m_layer_table|LayerTable)[\s\S]{{0,180}}"
            rf"{re.escape(target_layer_var)}\s*\.\s*index[\s\S]{{0,180}}"
            r"\.\s*Id\s*\(",
            metadata_source,
        ) or (
            re.search(r"(?:\[\s*\"id\"\s*\]|\{\s*\"id\"|,\s*\"id\")", metadata_source)
            and re.search(
                rf"\b{re.escape(target_layer_var)}\s*\.\s*index\b", metadata_source
            )
            and re.search(r"(?:\.\s*Id\s*\(|LayerId|layerId|UuidToString)", metadata_source)
        )
        has_path = re.search(
            rf"\b{re.escape(target_layer_var)}\s*\.\s*(?:path|fullPath)\b",
            metadata_source,
        ) or _metadata_source_uses_alias(
            metadata_source, "path", path_aliases
        )
        if has_shape and has_index and has_id and has_path:
            return

    raise AssertionError(
        "HandleObjectSetLayer must return top-level layer metadata with "
        "input, index, id, and path from the resolved layer"
    )


def _lookup_backed_userstrings_readback_expressions(body: str) -> list[str]:
    lookup_pattern = re.compile(
        r"(?:const\s+)?(?:auto|CRhinoObject|[\w:<>]+)\s*(?:\*\s*)?"
        r"(\w+)\s*=\s*(?:(?:[A-Za-z_]\w*\s*(?:->|\.|::))*)"
        r"(?:LookupActiveObjectStrict|LookupObject|LookupObjectStrict)\s*\("
    )

    expressions: list[str] = []
    for lookup in lookup_pattern.finditer(body):
        looked_up_var = lookup.group(1)
        readback_pattern = (
            rf"SerializeUserStringsFromAttributes\s*\(\s*"
            rf"{re.escape(looked_up_var)}\s*->\s*Attributes\s*\(\s*\)\s*\)"
        )
        if re.search(readback_pattern, body[lookup.end() :]):
            expressions.append(readback_pattern)
    return expressions


def _value_flows_to_response_userstrings(
    body: str, value_pattern: str, visited: set[str] | None = None
) -> bool:
    if visited is None:
        visited = set()

    if any(
        _expression_matches_value_pattern(value, value_pattern)
        for value in _iter_per_object_userstrings_values(body)
    ):
        return True

    for assignment in _iter_variable_assignments(body):
        if not _expression_matches_value_pattern(assignment.group(2), value_pattern):
            continue
        variable = assignment.group(1)
        if variable in visited:
            continue
        visited.add(variable)
        if _value_flows_to_response_userstrings(
            body, rf"\b{re.escape(variable)}\b", visited
        ):
            return True

    return False


def _assert_usertext_readback_after_modify(source: str, body: str) -> None:
    modify_match = re.search(r"\bModifyObjectAttributes\s*\(", body)
    assert modify_match, "Handler must call ModifyObjectAttributes before readback"

    post_mutation_body = body[modify_match.end() :]
    for readback_expression in _lookup_backed_userstrings_readback_expressions(
        post_mutation_body
    ):
        if _value_flows_to_response_userstrings(post_mutation_body, readback_expression):
            return

    helper_call_names = {
        match.group(1)
        for match in re.finditer(
            r"\b(\w*(?:Readback|Read|Serialize|UserStrings|Lookup)\w*)\s*\(",
            post_mutation_body,
        )
    }
    for helper_name in sorted(helper_call_names):
        try:
            helper_body = _extract_named_function(source, helper_name)
        except AssertionError:
            continue
        if not _lookup_backed_userstrings_readback_expressions(helper_body):
            continue
        helper_expression = rf"{re.escape(helper_name)}\s*\([^;{{}}]*\)"
        if _value_flows_to_response_userstrings(post_mutation_body, helper_expression):
            return

    raise AssertionError(
        "Handler must put lookup-backed post-mutation userStrings readback into "
        "the returned per-object userStrings field"
    )


def _extract_batch_userstrings_validation_body(source: str, parser_body: str) -> str:
    combined_bodies = [parser_body]
    pending = [
        match.group(1)
        for match in re.finditer(
            r"\b(ValidateBatchUserStrings|Validate\w*UserStrings\w*)\s*\(",
            parser_body,
        )
    ]
    seen: set[str] = set()

    while pending:
        helper_name = pending.pop(0)
        if helper_name in seen:
            continue
        seen.add(helper_name)
        try:
            helper_body = _extract_named_function(source, helper_name)
        except AssertionError:
            continue
        combined_bodies.append(helper_body)
        pending.extend(
            match.group(1)
            for match in re.finditer(
                r"\b(ValidateBatchUserStrings|Validate\w*UserStrings\w*)\s*\(",
                helper_body,
            )
        )

    return "\n".join(combined_bodies)


def _extract_userstrings_loop_body(helper_body: str) -> str:
    aliases = {"userStrings"}
    aliases.update(
        re.findall(
            r"\b(?:const\s+)?(?:auto|nlohmann::json|json|[\w:<>,]+)"
            r"\s*(?:[&*]\s*)?(\w+)\s*=\s*[^;]*"
            r"(?:\[\s*\"userStrings\"\s*\]|\.at\s*\(\s*\"userStrings\"\s*\)"
            r"|\.value\s*\(\s*\"userStrings\"\s*,)",
            helper_body,
        )
    )
    aliases.update(
        re.findall(r"\b(\w*userStrings\w*)\b", helper_body, re.IGNORECASE)
    )
    for params in re.findall(
        r"\bValidate\w*UserStrings\w*\s*\(([^)]*)\)\s*\{", helper_body
    ):
        aliases.update(re.findall(r"\b([A-Za-z_]\w*)\s*(?:,|$)", params))

    loop_bodies: list[str] = []
    for alias in sorted(aliases):
        for userstrings_iteration in re.finditer(
            rf"for\s*\([\s\S]{{0,360}}\b{re.escape(alias)}\b[\s\S]{{0,360}}\)\s*\{{",
            helper_body,
        ):
            body_start = helper_body.find(
                "{", userstrings_iteration.start(), userstrings_iteration.end()
            )
            loop_bodies.append(
                _extract_braced_source(
                    helper_body,
                    userstrings_iteration.start(),
                    body_start,
                    "userStrings validation loop",
                )
            )

    assert loop_bodies, "Parser path must iterate userStrings entries"
    return "\n".join(loop_bodies)


def _assert_throwing_if(loop_body: str, condition_pattern: str, message: str) -> None:
    assert re.search(
        rf"if\s*\([\s\S]{{0,220}}{condition_pattern}[\s\S]{{0,220}}\)"
        r"[\s\S]{0,220}throw",
        loop_body,
    ), message


def _assert_usertext_parser_rejects_invalid_values(validation_body: str) -> None:
    loop_body = _extract_userstrings_loop_body(validation_body)

    structured_bindings = re.findall(
        r"for\s*\([\s\S]{0,240}\[\s*(\w+)\s*,\s*(\w+)\s*\]"
        r"[\s\S]{0,240}\)\s*\{",
        loop_body,
    )
    key_vars = set(
        re.findall(
            r"\b(?:const\s+)?(?:auto|std::string|ON_wString)\s*(?:[&*]\s*)?"
            r"(\w+)\s*=\s*[^;]*\.\s*key\s*\(\s*\)",
            loop_body,
        )
    )
    key_vars.update(key for key, _value in structured_bindings)
    value_json_vars = set(
        re.findall(
            r"\b(?:const\s+)?(?:auto|nlohmann::json)\s*(?:[&*]\s*)?"
            r"(\w+)\s*=\s*[^;]*(?:\.\s*value\s*\(\s*\)|\b\w+\s*\[[^\]]+\]|\.at\s*\()",
            loop_body,
        )
    )
    value_json_vars.update(value for _key, value in structured_bindings)
    value_string_vars = set(
        re.findall(
            r"\b(?:const\s+)?(?:auto|std::string|ON_wString)\s*(?:[&*]\s*)?"
            r"(\w+)\s*=\s*[^;]*(?:\.\s*get\s*<\s*std::string\s*>\s*\(\s*\)"
            r"|Utf8ToWide\s*\(|WideToUtf8\s*\(|\.value\s*\(\s*\))",
            loop_body,
        )
    )

    key_empty_exprs = [r"\.\s*key\s*\(\s*\)\s*\.\s*empty\s*\(\s*\)"]
    key_empty_exprs += [
        rf"\b{re.escape(var)}\s*\.\s*empty\s*\(\s*\)" for var in key_vars
    ]
    _assert_throwing_if(
        loop_body,
        r"(?:{})".format("|".join(key_empty_exprs)),
        "Validation helper must reject empty userStrings keys",
    )

    json_value_exprs = [r"\.\s*value\s*\(\s*\)\s*\.\s*is_string\s*\(\s*\)"]
    json_value_exprs += [
        rf"\b{re.escape(var)}\s*\.\s*is_string\s*\(\s*\)"
        for var in value_json_vars
    ]
    _assert_throwing_if(
        loop_body,
        r"!\s*(?:{})".format("|".join(json_value_exprs)),
        "Validation helper must reject non-string userStrings values",
    )

    string_empty_exprs = [
        r"\.\s*get\s*<\s*std::string\s*>\s*\(\s*\)\s*\.\s*empty\s*\(\s*\)"
    ]
    string_empty_exprs += [
        rf"\b{re.escape(var)}\s*\.\s*empty\s*\(\s*\)"
        for var in value_string_vars
    ]
    _assert_throwing_if(
        loop_body,
        r"(?:{})".format("|".join(string_empty_exprs)),
        "Validation helper must reject empty userStrings string values",
    )


def _extract_serializer_with_fields(
    source: str, preferred_names: tuple[str, ...], fields: tuple[str, ...]
) -> tuple[str, str]:
    for name in preferred_names:
        try:
            body = _extract_named_function(source, name)
        except AssertionError:
            continue
        if all(field in body for field in fields):
            return name, body

    for match in re.finditer(r"\b(Serialize\w*State)\s*\(", source):
        name = match.group(1)
        try:
            body = _extract_named_function(source, name)
        except AssertionError:
            continue
        if all(field in body for field in fields):
            return name, body

    raise AssertionError(
        f"Missing serializer helper with fields: {', '.join(fields)}"
    )


def _assert_handler_uses_serializer_for_before_after(
    handler_body: str, serializer_name: str
) -> None:
    serializer_call_pattern = rf"{re.escape(serializer_name)}\s*\([^;{{}}]*\)"
    serializer_variables: dict[str, tuple[str, int]] = {}
    for assignment in _iter_variable_assignments(handler_body):
        if _expression_matches_value_pattern(
            assignment.group(2), serializer_call_pattern
        ):
            serializer_variables[assignment.group(1)] = (
                _normalize_expression_identity(assignment.group(2)),
                assignment.start(),
            )

    modify_match = re.search(r"\bModifyObjectAttributes\s*\(", handler_body)
    modify_position = modify_match.start() if modify_match else -1
    accepted_sources: dict[str, tuple[set[str], int]] = {}

    for key in ("before", "after"):
        occurrences = _iter_json_key_value_occurrences(handler_body, key)
        assert occurrences, f"Handler must assign {key} state"

        for value, position, _target, _kind in occurrences:
            accepted_identities: set[str] = set()
            source_position = position
            if _expression_matches_value_pattern(value, serializer_call_pattern):
                normalized = _normalize_expression_identity(value)
                accepted_identities = {f"expr:{normalized}"}
            else:
                for variable, (serialized_expression, assignment_position) in (
                    serializer_variables.items()
                ):
                    if _expression_matches_value_pattern(
                        value, rf"\b{re.escape(variable)}\b"
                    ):
                        accepted_identities = {
                            f"var:{variable}",
                            f"expr:{serialized_expression}",
                        }
                        source_position = assignment_position
                        break

            if not accepted_identities:
                continue
            if (
                key == "after"
                and modify_position != -1
                and source_position < modify_position
            ):
                continue
            accepted_sources[key] = (accepted_identities, source_position)
            break

        assert key in accepted_sources, (
            f"Handler must assign {key} from {serializer_name}(...) "
            "or a variable assigned from it"
        )

    reused_sources = accepted_sources["before"][0] & accepted_sources["after"][0]
    assert not reused_sources, (
        "Handler must not reuse the same serialized state source for before and after"
    )


def test_native_handler_declarations_exist():
    objects_header = OBJECTS_H.read_text(encoding="utf-8")
    usertext_header = USER_TEXT_H.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_H.read_text(encoding="utf-8")

    for name in ("HandleObjectVisibility", "HandleObjectSetLayer"):
        pattern = (
            rf"void\s+{name}\s*\(\s*const\s+httplib::Request&\s+req,\s*"
            rf"httplib::Response&\s+res\s*\)\s*;"
        )
        assert re.search(pattern, objects_header), (
            f"Missing ObjectsHandler declaration for {name}"
        )
        assert re.search(pattern, server_header), (
            f"Missing RookServer declaration for {name}"
        )

    assert re.search(
        r"void\s+HandleUserTextObjectSetBatch\s*\(\s*const\s+httplib::Request&\s+req,\s*"
        r"httplib::Response&\s+res\s*\)\s*;",
        usertext_header,
    )


def test_native_routes_are_registered():
    source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    _assert_post_route_delegates(
        source, "/objects/visibility", "HandleObjectVisibility(req, res);"
    )
    _assert_post_route_delegates(
        source, "/objects/set-layer", "HandleObjectSetLayer(req, res);"
    )
    _assert_post_route_delegates(
        source,
        "/usertext/object-set-batch",
        "Rook::Handlers::HandleUserTextObjectSetBatch(req, res);",
    )

    visibility_wrapper = _extract_function(
        source, "void CRookServer::HandleObjectVisibility"
    )
    set_layer_wrapper = _extract_function(
        source, "void CRookServer::HandleObjectSetLayer"
    )
    assert "Rook::Handlers::HandleObjectVisibility(req, res);" in visibility_wrapper
    assert "Rook::Handlers::HandleObjectSetLayer(req, res);" in set_layer_wrapper


def test_object_visibility_uses_modify_attributes_not_hide_show_selection_path():
    source = OBJECTS_CPP.read_text(encoding="utf-8")
    body = _extract_function(source, "void HandleObjectVisibility")
    parser_body = _extract_named_function(source, "ParseExactObjectIds")
    serializer_name, serializer_body = _extract_serializer_with_fields(
        source,
        ("SerializeObjectHygieneState", "SerializeObjectLayerState"),
        ("objectVisible", "layerVisible", "effectivelyVisible"),
    )

    assert "kMaxExactIdObjectBatchSize = 500" in source
    assert "ParseExactObjectIds" in body
    _assert_parser_enforces_batch_cap(parser_body, "kMaxExactIdObjectBatchSize")
    assert "RejectDuplicateUuid" in parser_body
    assert re.search(r"UndoScope\s+\w+\s*\(\s*pDoc\s*,\s*L\"Set Object Visibility\"\s*\)", body)
    _assert_set_visible_attrs_are_modified(body)
    assert "HideObject" not in body
    assert "ShowObject" not in body
    assert "objectVisible" in serializer_body
    assert "layerVisible" in serializer_body
    assert "effectivelyVisible" in serializer_body
    _assert_handler_uses_serializer_for_before_after(body, serializer_name)
    assert "EmitDirtyOperationError(res, ex)" in body
    assert "dirty_partial_state" in source


def test_object_set_layer_uses_resolve_layer_ref_and_modify_attributes():
    source = OBJECTS_CPP.read_text(encoding="utf-8")
    body = _extract_function(source, "void HandleObjectSetLayer")
    parser_body = _extract_named_function(source, "ParseExactObjectIds")
    target_layer_var = _extract_resolved_layer_variable(body)
    serializer_name, serializer_body = _extract_serializer_with_fields(
        source,
        ("SerializeObjectLayerState", "SerializeObjectHygieneState"),
        ("layerId",),
    )

    assert "kMaxExactIdObjectBatchSize = 500" in source
    assert "ParseExactObjectIds" in body
    assert "RejectDuplicateUuid" in parser_body
    assert re.search(r"UndoScope\s+\w+\s*\(\s*pDoc\s*,\s*L\"Set Object Layer\"\s*\)", body)
    _assert_set_layer_attrs_are_modified(body, target_layer_var)
    _assert_set_layer_response_metadata(body, target_layer_var)
    assert "layerId" in serializer_body
    _assert_handler_uses_serializer_for_before_after(body, serializer_name)
    assert "EmitDirtyOperationError(res, ex)" in body
    assert "dirty_partial_state" in source


def test_usertext_batch_uses_full_readback_and_batch_cap():
    source = USER_TEXT_CPP.read_text(encoding="utf-8")
    body = _extract_function(source, "void HandleUserTextObjectSetBatch")
    parser_body = _extract_named_function(source, "ParseUserTextSetBatchItems")
    validation_body = _extract_batch_userstrings_validation_body(source, parser_body)

    assert "kMaxUserTextObjectSetBatchItems = 500" in source
    assert "ParseUserTextSetBatchItems" in body
    _assert_parser_enforces_batch_cap(
        parser_body, "kMaxUserTextObjectSetBatchItems"
    )
    assert "RejectDuplicateUuid" in parser_body
    _assert_usertext_parser_rejects_invalid_values(validation_body)
    assert re.search(
        r"UndoScope\s+\w+\s*\(\s*pDoc\s*,\s*"
        r"L\"Set Object User Strings Batch\"\s*\)",
        body,
    )
    assert "ModifyObjectAttributes" in body
    _assert_usertext_readback_after_modify(source, body)
    assert "EmitDirtyUserTextOperationError(res, ex)" in body
    assert "dirty_partial_state" in source


def test_batch_caps_are_explicit_500_not_schema_only():
    objects_source = OBJECTS_CPP.read_text(encoding="utf-8")
    usertext_source = USER_TEXT_CPP.read_text(encoding="utf-8")

    assert "kMaxExactIdObjectBatchSize = 500" in objects_source
    assert "cannot exceed 500 ids" in objects_source
    assert "kMaxUserTextObjectSetBatchItems = 500" in usertext_source
    assert "cannot exceed 500 objects" in usertext_source
