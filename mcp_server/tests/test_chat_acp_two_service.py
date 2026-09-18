from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rook.agent.chat.acp_conversation import CreateConversationRequest, PromptInput
from rook.agent.chat.acp_presentation import PresentationCache
from rook.agent.chat.acp_storage import AssociationStore, SessionRecoveryRequired

from .test_chat_acp_conversation import (
    FakeProcessFactory,
    FakeRuntimeCatalog,
    NullSink,
    _binding,
    _contract,
    _paths,
)
from rook.agent.chat.acp_conversation import AcpConversationManager


async def _materialized_manager(tmp_path: Path):
    paths = _paths(tmp_path)
    store = AssociationStore(paths)
    contract = _contract(tmp_path)
    factory = FakeProcessFactory()
    manager = AcpConversationManager(
        store,
        FakeRuntimeCatalog(contract),
        factory,
        PresentationCache(paths.presentation_root),
    )
    saved = tmp_path / "saved"
    saved.mkdir(exist_ok=True)
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    prompt = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await prompt.result_task
    await manager.close(view.conversation_id)
    return manager, view, paths, contract


@pytest.mark.asyncio
async def test_two_services_contend_before_second_prime_launch(tmp_path: Path):
    first, view, paths, contract = await _materialized_manager(tmp_path)
    first_factory = FakeProcessFactory()
    first = AcpConversationManager(
        AssociationStore(paths),
        FakeRuntimeCatalog(contract),
        first_factory,
        PresentationCache(paths.presentation_root),
    )
    second_factory = FakeProcessFactory()
    second = AcpConversationManager(
        AssociationStore(paths),
        FakeRuntimeCatalog(contract),
        second_factory,
        PresentationCache(paths.presentation_root),
    )

    await first.reopen(view.conversation_id)
    with pytest.raises(SessionRecoveryRequired):
        await second.reopen(view.conversation_id)
    assert first_factory.launch_count == 1
    assert second_factory.launch_count == 0
    await first.close(view.conversation_id)


@pytest.mark.asyncio
async def test_crash_left_claim_refuses_reopen_and_delete_without_pid_lookup(tmp_path: Path):
    manager, view, paths, contract = await _materialized_manager(tmp_path)
    association = AssociationStore(paths).get(view.conversation_id)
    script = (
        "from pathlib import Path\n"
        "from rook.agent.chat.acp_storage import OpenClaim\n"
        f"OpenClaim.acquire(Path({str(paths.claims_root)!r}), {association.session_path!r})\n"
    )
    completed = subprocess.run([sys.executable, "-c", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    replacement = AcpConversationManager(
        AssociationStore(paths),
        FakeRuntimeCatalog(contract),
        FakeProcessFactory(),
        PresentationCache(paths.presentation_root),
    )

    with pytest.raises(SessionRecoveryRequired):
        await replacement.reopen(view.conversation_id)
    with pytest.raises(SessionRecoveryRequired):
        await replacement.delete(view.conversation_id)
