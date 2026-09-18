from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
VERIFIER = REPO / "scripts/verify-rookchat-acp-cutover.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("rookchat_acp_cutover", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write(root: Path, relative: str, text: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


OBSOLETE_PATH_CASES = (
    ("python-conversation-store", "mcp_server/src/rook/agent/chat/conversation_store.py"),
    ("python-chat-runner", "mcp_server/src/rook/agent/chat/chat_runner.py"),
    ("python-model-status", "mcp_server/src/rook/agent/chat/model_status.py"),
    ("python-prompt-builder", "mcp_server/src/rook/agent/chat/prompt_builder.py"),
    ("python-worker-first", "mcp_server/src/rook/agent/worker_first_csharp_application.py"),
    ("script-headless-qualification", "scripts/chatrunner_headless_qualification.py"),
    ("managed-claude-code-tab", "src/Rook/UI/Chat/ClaudeCodeTab.cs"),
    ("managed-claude-code-wrapper", "src/Rook/UI/Chat/ClaudeCodeWrapper.cs"),
    ("managed-panel-mcp-builder", "src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs"),
    ("managed-settings-dialog", "src/Rook/UI/Chat/SettingsDialog.cs"),
    ("managed-stream-json-parser", "src/Rook/UI/Chat/StreamJsonParser.cs"),
    ("managed-panel-mcp-builder-test", "src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs"),
    ("embedded-prototype", "src/Rook/UI/Chat/Resources/prototype.html"),
)


FORBIDDEN_TEXT_CASES = (
    (
        "import-conversation-store",
        "mcp_server/src/rook/agent/chat/live.py",
        "from rook.agent.chat.conversation_store import Legacy\n",
        "obsolete_import",
    ),
    (
        "import-chat-runner",
        "mcp_server/src/rook/agent/chat/live.py",
        "from rook.agent.chat.chat_runner import Legacy\n",
        "obsolete_import",
    ),
    (
        "import-model-status",
        "mcp_server/src/rook/agent/chat/live.py",
        "from rook.agent.chat.model_status import Legacy\n",
        "obsolete_import",
    ),
    (
        "import-prompt-builder",
        "mcp_server/src/rook/agent/chat/live.py",
        "from rook.agent.chat.prompt_builder import Legacy\n",
        "obsolete_import",
    ),
    (
        "import-worker-first",
        "mcp_server/src/rook/agent/chat/live.py",
        "from rook.agent.worker_first_csharp_application import Legacy\n",
        "obsolete_import",
    ),
    *(
        (
            f"route-{route.rsplit('/', 1)[-1]}",
            "mcp_server/src/rook/server.py",
            f"route = '{route}'\n",
            "obsolete_route",
        )
        for route in (
            "/agent/chat/personas",
            "/agent/chat/model",
            "/agent/chat/models",
            "/agent/chat/start",
            "/agent/chat/message",
            "/agent/chat/stop",
            "/agent/chat/ui-response",
            "/agent/chat/worker-first",
        )
    ),
    *(
        (f"direct-claude-{symbol}", "src/Rook/UI/Chat/Legacy.cs", f"class {symbol} {{}}\n", "legacy_direct_claude")
        for symbol in ("ClaudeCodeTab", "ClaudeCodeWrapper", "ClaudePanelMcpConfigBuilder")
    ),
    *(
        (f"private-prime-{symbol}", "mcp_server/src/rook/agent/chat/live.py", f"value = '{symbol}'\n", "private_prime_transport")
        for symbol in ("PrimeRpcProcess", "PrimeRpcClient", "prime_rpc", "AgentConnection")
    ),
    *(
        (f"daemon-{symbol}", "mcp_server/src/rook/agent/chat/live.py", f"value = '{symbol}'\n", "daemon_topology")
        for symbol in (
            "DaemonClient",
            "PrimeDaemonClient",
            "DaemonAgentConnection",
            "daemonTransport",
            "daemon_transport",
            "daemonSocket",
            "daemon_socket",
            "--daemon-socket",
            "PrimeWorkerProcess",
            "workerProcess",
            "worker_process",
            "prime_worker",
        )
    ),
    *(
        (f"process-start-{symbol}", "mcp_server/src/rook/agent/chat/live.py", f"value = '{symbol}'\n", "process_start_authority")
        for symbol in ("processStartUtcTicks", "process_start_utc_ticks", "processStartTicks", "process_start_ticks")
    ),
    *(
        (f"backend-{symbol}", "mcp_server/src/rook/agent/chat/live.py", f"value = '{symbol}'\n", "backend_abstraction")
        for symbol in (
            "availableBackends",
            "available_backends",
            "backendRegistry",
            "backend_registry",
            "backendSelector",
            "backend_selector",
            "ChatRunnerBackend",
        )
    ),
    (
        "surveillance-powershell-first",
        "mcp_server/src/rook/agent/chat/live.py",
        "subprocess.run(['powershell', 'Get-Process'])\n",
        "process_surveillance",
    ),
    (
        "surveillance-get-process-first",
        "mcp_server/src/rook/agent/chat/live.py",
        "command = 'Get-Process via powershell'\n",
        "process_surveillance",
    ),
    *(
        (f"surveillance-{symbol}", "mcp_server/src/rook/agent/chat/live.py", f"value = '{symbol}'\n", "process_surveillance")
        for symbol in ("psutil.process_iter", "CreateToolhelp32Snapshot", "kill-by-name")
    ),
    (
        "csharp-acp-pascal",
        "src/Rook/UI/Chat/Legacy.cs",
        "using AgentClientProtocol;\n",
        "csharp_acp_owner",
    ),
    (
        "csharp-acp-kebab",
        "src/Rook/UI/Chat/Legacy.cs",
        "const string Package = \"agent-client-protocol\";\n",
        "csharp_acp_owner",
    ),
    (
        "non-python-acp-pascal",
        "src/Rook/UI/Chat/legacy.ts",
        "const packageName = 'AgentClientProtocol';\n",
        "non_python_acp_sdk",
    ),
    (
        "non-python-acp-kebab",
        "src/Rook/UI/Chat/legacy.ts",
        "import 'agent-client-protocol';\n",
        "non_python_acp_sdk",
    ),
    *(
        (
            f"runtime-evaluator-{segment}",
            "mcp_server/src/rook/agent/chat/service_main.py",
            f"from rook.{segment} import Legacy\n",
            "runtime_evaluator",
        )
        for segment in ("campaign", "qualification", "evaluator")
    ),
    (
        "ui-block-snake",
        "src/Rook/UI/Chat/Resources/chat.html",
        "const eventName = 'ui_block';\n",
        "obsolete_ui_block",
    ),
    (
        "ui-block-submit",
        "src/Rook/UI/Chat/Resources/chat.html",
        "const eventName = 'ui_block_submit';\n",
        "obsolete_ui_block",
    ),
    (
        "ui-block-render",
        "src/Rook/UI/Chat/Resources/chat.html",
        "function renderUIBlock() {}\n",
        "obsolete_ui_block",
    ),
    (
        "ui-block-update",
        "src/Rook/UI/Chat/Resources/chat.html",
        "function updateUIBlock() {}\n",
        "obsolete_ui_block",
    ),
    (
        "ui-block-css",
        "src/Rook/UI/Chat/Resources/chat.css",
        ".ui-block { display: block; }\n",
        "obsolete_ui_block",
    ),
)


def test_clean_acp_only_fixture_passes(tmp_path: Path) -> None:
    module = load_verifier()
    write(tmp_path, "mcp_server/src/rook/agent/chat/service_main.py", "from .acp_conversation import AcpConversationManager\n")
    write(tmp_path, "mcp_server/src/rook/agent/chat/acp_conversation.py", "class AcpConversationManager: pass\n")
    write(tmp_path, "src/Rook/UI/Chat/AgentChatClient.cs", "namespace Rook.UI.Chat { class AgentChatClient {} }\n")

    assert module.scan(tmp_path) == []


@pytest.mark.parametrize(
    ("case_name", "relative"),
    OBSOLETE_PATH_CASES,
    ids=[case[0] for case in OBSOLETE_PATH_CASES],
)
def test_cutover_scanner_rejects_each_obsolete_path(
    tmp_path: Path,
    case_name: str,
    relative: str,
) -> None:
    module = load_verifier()
    write(tmp_path, relative)

    findings = module.scan(tmp_path)

    assert findings == [module.Finding("obsolete_path", relative, "obsolete RookChat implementation remains")], case_name


@pytest.mark.parametrize(
    ("case_name", "relative", "text", "expected"),
    FORBIDDEN_TEXT_CASES,
    ids=[case[0] for case in FORBIDDEN_TEXT_CASES],
)
def test_cutover_scanner_rejects_each_forbidden_spelling(
    tmp_path: Path,
    case_name: str,
    relative: str,
    text: str,
    expected: str,
) -> None:
    module = load_verifier()
    write(tmp_path, relative, text)

    findings = module.scan(tmp_path)

    assert len(findings) == 1, case_name
    assert findings[0].code == expected, case_name
    assert findings[0].path == relative, case_name


def test_cutover_scanner_rejects_unreadable_product_source(tmp_path: Path) -> None:
    module = load_verifier()
    relative = "mcp_server/src/rook/agent/chat/broken.py"
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff")

    findings = module.scan(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "unreadable_product_source"
    assert findings[0].path == relative


def test_cutover_scanner_preserves_non_chat_provider_consumers(tmp_path: Path) -> None:
    module = load_verifier()
    write(
        tmp_path,
        "mcp_server/src/rook/learning/agent.py",
        "CLAUDE = 'claude'\nLITELLM = 'litellm'\nDSPY = 'dspy'\nCHIRP = 'chirp'\n",
    )

    assert module.scan(tmp_path) == []


def test_repository_has_only_the_prime_acp_chat_product() -> None:
    module = load_verifier()
    assert module.scan(REPO) == []
