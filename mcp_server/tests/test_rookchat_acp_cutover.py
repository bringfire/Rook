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


def test_clean_acp_only_fixture_passes(tmp_path: Path) -> None:
    module = load_verifier()
    write(tmp_path, "mcp_server/src/rook/agent/chat/service_main.py", "from .acp_conversation import AcpConversationManager\n")
    write(tmp_path, "mcp_server/src/rook/agent/chat/acp_conversation.py", "class AcpConversationManager: pass\n")
    write(tmp_path, "src/Rook/UI/Chat/AgentChatClient.cs", "namespace Rook.UI.Chat { class AgentChatClient {} }\n")

    assert module.scan(tmp_path) == []


@pytest.mark.parametrize(
    ("relative", "text", "expected"),
    [
        ("mcp_server/src/rook/agent/chat/chat_runner.py", "", "obsolete_path"),
        ("mcp_server/src/rook/agent/chat/live.py", "from rook.agent.chat.conversation_store import ConversationStore\n", "obsolete_import"),
        ("mcp_server/src/rook/server.py", "route = '/agent/chat/model'\n", "obsolete_route"),
        ("mcp_server/src/rook/agent/chat/live.py", "availableBackends = []\n", "backend_abstraction"),
        ("mcp_server/src/rook/agent/chat/live.py", "AgentConnection()\n", "private_prime_transport"),
        ("mcp_server/src/rook/agent/chat/live.py", "subprocess.run(['powershell', 'Get-Process'])\n", "process_surveillance"),
        ("src/Rook/UI/Chat/AgentChatClient.cs", "using AgentClientProtocol;\n", "csharp_acp_owner"),
        ("src/Rook/UI/Chat/chat.ts", "import 'agent-client-protocol';\n", "non_python_acp_sdk"),
        ("mcp_server/src/rook/agent/chat/service_main.py", "from rook.qualification.campaign import Evaluator\n", "runtime_evaluator"),
    ],
)
def test_cutover_scanner_rejects_forbidden_product_surface(
    tmp_path: Path,
    relative: str,
    text: str,
    expected: str,
) -> None:
    module = load_verifier()
    write(tmp_path, relative, text)

    findings = module.scan(tmp_path)

    assert any(finding.code == expected and finding.path == relative for finding in findings)


def test_repository_has_only_the_prime_acp_chat_product() -> None:
    module = load_verifier()
    assert module.scan(REPO) == []
