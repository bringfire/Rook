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
