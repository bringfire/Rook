#!/usr/bin/env python3
"""Verify that shipped RookChat surfaces contain only the Prime ACP backend."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path
from typing import Iterable, NamedTuple


class Finding(NamedTuple):
    code: str
    path: str
    message: str


_FORBIDDEN_PATHS = (
    "mcp_server/src/rook/agent/chat/conversation_store.py",
    "mcp_server/src/rook/agent/chat/chat_runner.py",
    "mcp_server/src/rook/agent/chat/model_status.py",
    "mcp_server/src/rook/agent/chat/prompt_builder.py",
    "mcp_server/src/rook/agent/worker_first_csharp_application.py",
    "scripts/chatrunner_headless_qualification.py",
    "src/Rook/UI/Chat/ClaudeCodeTab.cs",
    "src/Rook/UI/Chat/ClaudeCodeWrapper.cs",
    "src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs",
    "src/Rook/UI/Chat/SettingsDialog.cs",
    "src/Rook/UI/Chat/StreamJsonParser.cs",
    "src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs",
    "src/Rook/UI/Chat/Resources/prototype.html",
)

_PRODUCT_ROOTS = (
    "mcp_server/src/rook",
    "src/Rook",
    "installer",
    "scripts",
)

_TEXT_SUFFIXES = frozenset({".cs", ".css", ".html", ".iss", ".js", ".py", ".ps1", ".sh", ".ts"})
_OBSOLETE_IMPORT = re.compile(
    r"(?:from|import)\s+rook\.agent\.(?:chat\.(?:conversation_store|chat_runner|model_status|prompt_builder)|worker_first_csharp_application)\b"
)
_OBSOLETE_ROUTE = re.compile(
    r"/agent/chat/(?:personas|models?|start|message|stop|ui-response|worker-first)(?:[/'\"\s]|$)"
)
_LEGACY_DIRECT_CLAUDE = re.compile(r"\b(?:ClaudeCodeTab|ClaudeCodeWrapper|ClaudePanelMcpConfigBuilder)\b")
_PRIVATE_PRIME_TRANSPORT = re.compile(r"\b(?:PrimeRpcProcess|PrimeRpcClient|prime_rpc|AgentConnection)\b")
_DAEMON_TOPOLOGY = re.compile(
    r"(?:\b(?:DaemonClient|PrimeDaemonClient|DaemonAgentConnection|daemonTransport|daemon_transport|daemonSocket|"
    r"daemon_socket|PrimeWorkerProcess|workerProcess|worker_process|prime_worker)\b|--daemon-socket)"
)
_PROCESS_START_AUTHORITY = re.compile(
    r"\b(?:processStartUtcTicks|process_start_utc_ticks|processStartTicks|process_start_ticks)\b"
)
_BACKEND_ABSTRACTION = re.compile(
    r"\b(?:availableBackends|available_backends|backendRegistry|backend_registry|backendSelector|backend_selector|"
    r"ChatRunnerBackend)\b"
)
_PROCESS_SURVEILLANCE = re.compile(
    r"(?is)(?:powershell[^\n]{0,160}Get-Process|Get-Process[^\n]{0,160}powershell|psutil\.process_iter|CreateToolhelp32Snapshot|kill-by-name)"
)
_OBSOLETE_UI_BLOCK = re.compile(r"(?:\b(?:ui_block|ui_block_submit|renderUIBlock|updateUIBlock)\b|\.ui-block\b)")
_ACP_SDK = re.compile(r"agent-client-protocol|\bAgentClientProtocol\b", re.IGNORECASE)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_product_files(root: Path) -> Iterable[Path]:
    verifier = (root / "scripts/verify-rookchat-acp-cutover.py").resolve()
    for relative_root in _PRODUCT_ROOTS:
        base = root / relative_root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            if path.resolve() == verifier:
                continue
            if "tests" in path.relative_to(base).parts:
                continue
            yield path


def _runtime_evaluator_import(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = (node.module or "",)
        else:
            continue
        if any(part in name.lower().split(".") for name in names for part in ("campaign", "qualification", "evaluator")):
            return True
    return False


def scan(root: Path) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []

    for relative in _FORBIDDEN_PATHS:
        if (root / relative).is_file():
            findings.append(Finding("obsolete_path", relative, "obsolete RookChat implementation remains"))

    for path in _iter_product_files(root):
        relative = _relative(root, path)
        is_chat_surface = relative.startswith("mcp_server/src/rook/agent/chat/") or relative.startswith(
            "src/Rook/UI/Chat/"
        )
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(Finding("unreadable_product_source", relative, str(exc)))
            continue

        checks = [
            ("obsolete_import", _OBSOLETE_IMPORT, "obsolete RookChat import remains"),
            ("obsolete_route", _OBSOLETE_ROUTE, "obsolete RookChat HTTP route remains"),
        ]
        if is_chat_surface:
            checks.extend(
                (
                    ("legacy_direct_claude", _LEGACY_DIRECT_CLAUDE, "legacy direct-Claude RookChat implementation remains"),
                    ("private_prime_transport", _PRIVATE_PRIME_TRANSPORT, "private Prime transport remains"),
                    ("daemon_topology", _DAEMON_TOPOLOGY, "daemon or worker topology remains"),
                    ("process_start_authority", _PROCESS_START_AUTHORITY, "process-start identity authority remains"),
                    ("backend_abstraction", _BACKEND_ABSTRACTION, "RookChat backend abstraction remains"),
                    ("process_surveillance", _PROCESS_SURVEILLANCE, "process surveillance remains"),
                    ("obsolete_ui_block", _OBSOLETE_UI_BLOCK, "obsolete adaptive UI block remains"),
                )
            )
        for code, pattern, message in checks:
            if pattern.search(text):
                findings.append(Finding(code, relative, message))

        if path.suffix.lower() == ".cs" and _ACP_SDK.search(text):
            findings.append(Finding("csharp_acp_owner", relative, "C# must not own the ACP SDK"))
        elif path.suffix.lower() != ".py" and _ACP_SDK.search(text):
            findings.append(Finding("non_python_acp_sdk", relative, "only Python may import the ACP SDK"))

        if relative.startswith("mcp_server/src/rook/") and path.suffix.lower() == ".py" and _runtime_evaluator_import(text):
            findings.append(Finding("runtime_evaluator", relative, "product runtime imports external qualification machinery"))

    return sorted(findings, key=lambda finding: (finding.path, finding.code, finding.message))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()

    findings = scan(args.root)
    if findings:
        for finding in findings:
            print(f"{finding.code}: {finding.path}: {finding.message}")
        return 1

    print("RookChat ACP cutover verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
