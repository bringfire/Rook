"""LM2G external_mcp public-wire-surface audit (read-only).

Reconciles the advertised public MCP catalog (server.list_tools names) against
the wire-dispatch handler names extracted by static AST parsing of
server._call_tool_dispatch. Standalone diagnostic report -- NOT an execution
profile. Never imports/executes rook.server, instantiates no ToolRegistry,
calls no tool, and mutates no schema/visibility/wire behavior.

Stdlib-only: ast, dataclasses, importlib.util, os (+ the Severity literal).
"""

from __future__ import annotations

import ast
import importlib.util
import os
from collections.abc import Iterable
from dataclasses import dataclass

from rook.agent.capability_record import Severity

_DISPATCH_FUNCTION = "_call_tool_dispatch"

_SEVERITY_BY_CODE: dict[str, Severity] = {
    "advertised_not_dispatchable": "error",
    "handler_not_advertised": "info",
    "empty_catalog": "error",
    "dispatch_function_missing": "error",
    "wire_source_unresolved": "error",
    "multiple_dispatch_matches": "warning",
    "unextractable_case": "warning",
}


@dataclass(frozen=True)
class ExternalMcpFinding:
    code: str
    tool: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class WireDispatchEvidence:
    names: tuple[str, ...]
    findings: tuple[ExternalMcpFinding, ...]


@dataclass(frozen=True)
class ExternalMcpResolution:
    advertised_names: tuple[str, ...]
    wire_dispatch_names: tuple[str, ...]
    findings: tuple[ExternalMcpFinding, ...]


def _finding(code: str, tool: str, message: str) -> ExternalMcpFinding:
    return ExternalMcpFinding(
        code=code, tool=tool, severity=_SEVERITY_BY_CODE[code], message=message
    )


def _sorted_findings(
    findings: Iterable[ExternalMcpFinding],
) -> tuple[ExternalMcpFinding, ...]:
    return tuple(sorted(findings, key=lambda f: (f.code, f.tool, f.severity)))


def _subject_is_name(subject: ast.expr) -> bool:
    return isinstance(subject, ast.Name) and subject.id == "name"


def _string_value(pat: ast.pattern) -> str | None:
    if (
        isinstance(pat, ast.MatchValue)
        and isinstance(pat.value, ast.Constant)
        and isinstance(pat.value.value, str)
    ):
        return pat.value.value
    return None


def _is_wildcard(pat: ast.pattern) -> bool:
    return isinstance(pat, ast.MatchAs) and pat.pattern is None and pat.name is None


def _unextractable(node: ast.AST, reason: str) -> ExternalMcpFinding:
    line = getattr(node, "lineno", -1)
    return _finding(
        "unextractable_case",
        f"line {line}",
        f"Unextractable case ({reason}) at line {line}; skipped.",
    )


def _harvest_case(
    case: ast.match_case,
    names: set[str],
    findings: list[ExternalMcpFinding],
) -> None:
    pat = case.pattern
    if case.guard is not None:
        findings.append(_unextractable(pat, "guarded case"))
        return
    value = _string_value(pat)
    if value is not None:
        names.add(value)
        return
    if isinstance(pat, ast.MatchOr):
        for sub in pat.patterns:
            sub_value = _string_value(sub)
            if sub_value is not None:
                names.add(sub_value)
            else:
                findings.append(_unextractable(sub, "non-string OR sub-pattern"))
        return
    if _is_wildcard(pat):
        return
    findings.append(_unextractable(pat, "non-constant case pattern"))


def extract_wire_dispatch_evidence_from_source(source: str) -> WireDispatchEvidence:
    """Pure AST extraction of wire-handler names from a source string.

    Locates the function named _call_tool_dispatch and harvests string case
    labels from its `match name:` statement(s). No execution, no imports.
    """
    tree = ast.parse(source)
    func: ast.AST | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _DISPATCH_FUNCTION
        ):
            func = node
            break
    if func is None:
        return WireDispatchEvidence(
            names=(),
            findings=(
                _finding(
                    "dispatch_function_missing",
                    _DISPATCH_FUNCTION,
                    f"Function '{_DISPATCH_FUNCTION}' not found in source; "
                    f"cannot extract wire handlers.",
                ),
            ),
        )

    name_matches = [
        m
        for m in ast.walk(func)
        if isinstance(m, ast.Match) and _subject_is_name(m.subject)
    ]
    findings: list[ExternalMcpFinding] = []
    if len(name_matches) > 1:
        findings.append(
            _finding(
                "multiple_dispatch_matches",
                _DISPATCH_FUNCTION,
                f"{len(name_matches)} 'match name:' statements in "
                f"'{_DISPATCH_FUNCTION}'; expected exactly one.",
            )
        )

    names: set[str] = set()
    for match in name_matches:
        for case in match.cases:
            _harvest_case(case, names, findings)

    return WireDispatchEvidence(
        names=tuple(sorted(names)),
        findings=_sorted_findings(findings),
    )


def collect_wire_dispatch_evidence(
    module_name: str = "rook.server",
) -> WireDispatchEvidence:
    """Resolve a module's source via find_spec(...).origin and extract evidence.

    Reads the source FILE; never imports/executes the module. Provenance is
    caller-context-dependent: with the worktree importable, find_spec resolves
    the worktree source; under the deployed smoke (empty PYTHONPATH) it resolves
    deployed site-packages.

    A missing spec, a None/missing origin, or a non-file origin yields a
    structured wire_source_unresolved error -- never a raw traceback.
    """
    spec = None
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, AttributeError, ValueError):
        spec = None

    origin = getattr(spec, "origin", None) if spec is not None else None
    if not origin or not os.path.isfile(origin):
        return WireDispatchEvidence(
            names=(),
            findings=(
                _finding(
                    "wire_source_unresolved",
                    module_name,
                    f"Could not resolve a readable source file for module "
                    f"'{module_name}' (origin={origin!r}).",
                ),
            ),
        )

    try:
        with open(origin, encoding="utf-8") as handle:
            source = handle.read()
    except OSError as exc:
        return WireDispatchEvidence(
            names=(),
            findings=(
                _finding(
                    "wire_source_unresolved",
                    module_name,
                    f"Could not read source for module '{module_name}' at "
                    f"{origin!r}: {exc!r}.",
                ),
            ),
        )

    return extract_wire_dispatch_evidence_from_source(source)
