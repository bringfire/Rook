from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_CSHARP_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOP_LEVEL_USING_RE = re.compile(
    r"^\s*using\s+(?!\(|var\b)(?:(?:static\s+)?[A-Za-z_][A-Za-z0-9_.]*|"
    r"[A-Za-z_][A-Za-z0-9_]*\s*=\s*[A-Za-z_][A-Za-z0-9_.]*)\s*;",
    re.MULTILINE,
)
_CLASS_DECLARATION_RE = re.compile(r"\bclass\s+[A-Za-z_][A-Za-z0-9_]*\b")
_GH_COMPONENT_SUBCLASS_RE = re.compile(
    r":\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)*GH_Component\b"
)
_SCRIPT_INSTANCE_CLASS_RE = re.compile(r"\bpublic\s+class\s+Script_Instance\b")
_SCRIPT_INSTANCE_BASE_RE = re.compile(
    r"\bpublic\s+class\s+Script_Instance\s*:\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*GH_ScriptInstance\b"
)
_RUNSCRIPT_DECLARATION_RE = re.compile(
    r"\b(?P<visibility>public|private|protected|internal)\s+void\s+"
    r"RunScript\s*\((?P<parameters>[^()]*)\)"
)
_CONDITIONAL_PREPROCESSOR_RE = re.compile(
    r"^\s*#\s*(?:if|elif|else|endif|define|undef)\b",
    re.MULTILINE,
)
_WRONG_COMPONENT_PATTERNS: tuple[str, ...] = (
    "SolveInstance",
    "RegisterInputParams",
    "RegisterOutputParams",
    "IGH_DataAccess",
    "GH_InputParamManager",
    "GH_OutputParamManager",
)

_CSHARP_RESERVED_KEYWORDS = frozenset({
    "abstract", "as", "base", "bool", "break", "byte", "case", "catch",
    "char", "checked", "class", "const", "continue", "decimal", "default",
    "delegate", "do", "double", "else", "enum", "event", "explicit",
    "extern", "false", "finally", "fixed", "float", "for", "foreach",
    "goto", "if", "implicit", "in", "int", "interface", "internal", "is",
    "lock", "long", "namespace", "new", "null", "object", "operator",
    "out", "override", "params", "private", "protected", "public",
    "readonly", "ref", "return", "sbyte", "sealed", "short", "sizeof",
    "stackalloc", "static", "string", "struct", "switch", "this", "throw",
    "true", "try", "typeof", "uint", "ulong", "unchecked", "unsafe",
    "ushort", "using", "virtual", "void", "volatile", "while",
})


@dataclass(frozen=True)
class CSharpScriptPreflightResult:
    ok: bool
    message: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class CSharpRepresentationContractResult:
    ok: bool
    error_codes: tuple[str, ...]


def is_recognized_csharp_full_source(code: Any) -> bool:
    return isinstance(code, str) and (
        "class Script_Instance" in code or "void RunScript" in code
    )


def _failure(code: str, message: str) -> CSharpScriptPreflightResult:
    return CSharpScriptPreflightResult(ok=False, message=message, code=code)


def _validate_pin_names(
    pins_in: Sequence[Mapping[str, Any]],
    pins_out: Sequence[Mapping[str, Any]],
) -> CSharpScriptPreflightResult | None:
    seen: set[str] = set()
    for direction, pins in (("input", pins_in), ("output", pins_out)):
        for pin in pins:
            name = pin.get("name")
            if not isinstance(name, str) or not name.strip():
                return _failure("invalid_pin_name", f"C# {direction} pin name must be a non-empty string.")
            stripped = name.strip()
            if not _CSHARP_IDENTIFIER_RE.match(stripped):
                return _failure(
                    "invalid_pin_name",
                    f"C# {direction} pin name '{stripped}' is not a valid C# identifier.",
                )
            if stripped in _CSHARP_RESERVED_KEYWORDS:
                return _failure(
                    "reserved_pin_name",
                    f"C# {direction} pin name '{stripped}' is a reserved C# keyword.",
                )
            if stripped in seen:
                return _failure(
                    "duplicate_pin_name",
                    f"C# pin name '{stripped}' is duplicated across the script signature.",
                )
            seen.add(stripped)
    return None


def _complete_pin_declarations(
    pins: Sequence[Mapping[str, Any]],
) -> bool:
    for pin in pins:
        if set(pin) != {"name", "type", "access"}:
            return False
        type_name = pin.get("type")
        if not isinstance(type_name, str) or not type_name.strip():
            return False
        if pin.get("access") not in {"item", "list", "tree"}:
            return False
    return True


def _mask_csharp_noncode(source: str) -> str:
    """Mask comments and literals while preserving offsets and brace layout."""

    chars = list(source)

    def mask(start: int, end: int) -> None:
        for index in range(start, min(end, len(chars))):
            if chars[index] not in "\r\n":
                chars[index] = " "

    index = 0
    length = len(source)
    while index < length:
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            end = length if end < 0 else end
            mask(index, end)
            index = end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = length if end < 0 else end + 2
            mask(index, end)
            index = end
            continue

        quote_count = 0
        if source[index] == '"':
            while index + quote_count < length and source[index + quote_count] == '"':
                quote_count += 1
        if quote_count >= 3:
            delimiter = '"' * quote_count
            end = source.find(delimiter, index + quote_count)
            end = length if end < 0 else end + quote_count
            mask(index, end)
            index = end
            continue

        verbatim_prefix = next(
            (
                prefix
                for prefix in ('$@"', '@$"', '@"')
                if source.startswith(prefix, index)
            ),
            None,
        )
        if verbatim_prefix is not None:
            cursor = index + len(verbatim_prefix)
            while cursor < length:
                if source.startswith('""', cursor):
                    cursor += 2
                    continue
                if source[cursor] == '"':
                    cursor += 1
                    break
                cursor += 1
            mask(index, cursor)
            index = cursor
            continue

        regular_prefix = '$"' if source.startswith('$"', index) else None
        if regular_prefix is not None or source[index] == '"':
            cursor = index + (2 if regular_prefix is not None else 1)
            escaped = False
            while cursor < length:
                char = source[cursor]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    cursor += 1
                    break
                cursor += 1
            mask(index, cursor)
            index = cursor
            continue

        if source[index] == "'":
            cursor = index + 1
            escaped = False
            while cursor < length:
                char = source[cursor]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "'":
                    cursor += 1
                    break
                cursor += 1
            mask(index, cursor)
            index = cursor
            continue

        index += 1

    return "".join(chars)


def _brace_depth_at(source: str, position: int) -> int:
    depth = 0
    for char in source[:position]:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
    return depth


def _matching_brace(source: str, opening_index: int) -> int | None:
    depth = 0
    for index in range(opening_index, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                return None
    return None


def validate_rhinocode_csharp_full_source(
    *,
    code: Any,
    pins_in: Sequence[Mapping[str, Any]],
    pins_out: Sequence[Mapping[str, Any]],
) -> CSharpRepresentationContractResult:
    """Recognize the exact full-source boundary Rook sends to RhinoCode C#.

    This intentionally validates only the class and method envelope. RhinoCode
    compilation remains authoritative for the C# language and method body.
    """

    if not isinstance(code, str) or not code.strip():
        return CSharpRepresentationContractResult(
            ok=False,
            error_codes=("invalid_full_source",),
        )

    all_pins = [*pins_in, *pins_out]
    if (
        not _complete_pin_declarations(all_pins)
        or _validate_pin_names(pins_in, pins_out) is not None
    ):
        return CSharpRepresentationContractResult(
            ok=False,
            error_codes=("invalid_pin_declaration",),
        )

    structural_source = _mask_csharp_noncode(code)
    errors: list[str] = []
    if _CONDITIONAL_PREPROCESSOR_RE.search(structural_source):
        errors.append("conditional_compilation_forbidden")
    if _GH_COMPONENT_SUBCLASS_RE.search(structural_source):
        errors.append("gh_component_subclass_forbidden")

    script_class_declarations = tuple(
        match
        for match in _SCRIPT_INSTANCE_CLASS_RE.finditer(structural_source)
        if _brace_depth_at(structural_source, match.start()) == 0
    )
    base_declarations = tuple(
        match
        for match in _SCRIPT_INSTANCE_BASE_RE.finditer(structural_source)
        if _brace_depth_at(structural_source, match.start()) == 0
    )
    class_body: str | None = None
    if len(base_declarations) != 1:
        errors.append("missing_gh_script_instance_base")
    if len(script_class_declarations) == 1:
        class_declaration = script_class_declarations[0]
        class_open = structural_source.find("{", class_declaration.end())
        invalid_separator = min(
            (
                position
                for position in (
                    structural_source.find(";", class_declaration.end()),
                    structural_source.find("}", class_declaration.end()),
                )
                if position >= 0
            ),
            default=len(structural_source),
        )
        if class_open < 0 or invalid_separator < class_open:
            errors.append("invalid_full_source")
        else:
            class_close = _matching_brace(structural_source, class_open)
            if class_close is None:
                errors.append("invalid_full_source")
            else:
                class_body = structural_source[class_open + 1 : class_close]
    elif len(script_class_declarations) > 1:
        errors.append("invalid_full_source")

    declarations = tuple(
        match
        for match in _RUNSCRIPT_DECLARATION_RE.finditer(class_body or "")
        if _brace_depth_at(class_body or "", match.start()) == 0
    )
    if len(declarations) != 1:
        errors.append("runscript_method_count_mismatch")
    else:
        declaration = declarations[0]
        actual_parameters = tuple(
            re.sub(r"\s+", " ", parameter.strip())
            for parameter in declaration.group("parameters").split(",")
            if parameter.strip()
        )
        expected_parameters = tuple(
            [f'object {pin["name"]}' for pin in pins_in]
            + [f'ref object {pin["name"]}' for pin in pins_out]
        )
        if (
            declaration.group("visibility") != "private"
            or actual_parameters != expected_parameters
        ):
            errors.append("runscript_signature_mismatch")

    return CSharpRepresentationContractResult(
        ok=not errors,
        error_codes=tuple(errors),
    )


def preflight_csharp_script(
    *,
    code: Any,
    pins_in: Sequence[Mapping[str, Any]],
    pins_out: Sequence[Mapping[str, Any]],
    mode: str = "auto",
) -> CSharpScriptPreflightResult:
    if not isinstance(code, str) or not code.strip():
        return _failure("invalid_code", "C# script code must be a non-empty string.")

    pin_failure = _validate_pin_names(pins_in, pins_out)
    if pin_failure is not None:
        return pin_failure

    if _GH_COMPONENT_SUBCLASS_RE.search(code):
        return _failure(
            "wrong_component_category",
            (
                "C# script preflight failed because the code looks like a "
                "Grasshopper GH_Component plugin. RhinoCode C# Script expects "
                "body code or Script_Instance/RunScript source."
            ),
        )

    for pattern in _WRONG_COMPONENT_PATTERNS:
        if pattern in code:
            return _failure(
                "wrong_component_category",
                (
                    "C# script preflight failed because the code looks like a "
                    "Grasshopper GH_Component plugin. RhinoCode C# Script expects "
                    "body code or Script_Instance/RunScript source."
                ),
            )

    full_source = is_recognized_csharp_full_source(code)
    selected_mode = str(mode or "auto").strip().lower()
    body_style = selected_mode == "body" or (selected_mode == "auto" and not full_source)

    if body_style and _CLASS_DECLARATION_RE.search(code):
        return _failure(
            "body_contains_class",
            "C# body-style code cannot contain a class declaration; provide recognized full source instead.",
        )

    if body_style and _TOP_LEVEL_USING_RE.search(code):
        return _failure(
            "body_contains_using",
            "C# body-style code cannot contain top-level using directives.",
        )

    return CSharpScriptPreflightResult(ok=True)
