"""Tests for ConversationStore — conversation lifecycle management."""
import asyncio
import pytest
from rook.agent.chat.conversation_store import ConversationStore, Conversation


def test_create_conversation():
    store = ConversationStore()
    conv = store.create("explorer")
    assert conv.id.startswith("conv_")
    assert conv.persona == "explorer"
    assert conv.messages == []
    assert conv.active_run_id is None


def test_get_conversation():
    store = ConversationStore()
    conv = store.create("worker")
    retrieved = store.get(conv.id)
    assert retrieved is conv


def test_get_missing_returns_none():
    store = ConversationStore()
    assert store.get("conv_nonexistent") is None


def test_stop_conversation():
    store = ConversationStore()
    conv = store.create("explorer")
    cid = conv.id
    store.stop(cid)
    assert store.get(cid) is None


def test_max_conversations():
    store = ConversationStore(max_conversations=3)
    store.create("explorer")
    store.create("worker")
    store.create("scripter")
    with pytest.raises(RuntimeError, match="Max conversations"):
        store.create("specialist")


def test_list_conversations():
    store = ConversationStore()
    store.create("explorer")
    store.create("worker")
    convs = store.list_conversations()
    assert len(convs) == 2
    personas = {c["persona"] for c in convs}
    assert personas == {"explorer", "worker"}
