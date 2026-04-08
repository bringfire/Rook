"""Integration tests for the full agent chat flow."""
import json
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from rook.agent.chat.server import create_chat_app
from rook.agent.chat.conversation_store import ConversationStore
from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.chat.chat_runner import ChatRunner


class TestChatIntegration(AioHTTPTestCase):
    async def get_application(self):
        # Fresh instances for each test
        return create_chat_app(
            store=ConversationStore(),
            builder=PromptBuilder(),
            runner=ChatRunner(),
        )

    async def test_full_conversation_flow(self):
        """Start -> message -> stop lifecycle."""
        # Start
        resp = await self.client.post("/agent/chat/start", json={"persona": "worker"})
        assert resp.status == 200
        start_data = await resp.json()
        conv_id = start_data["conversation_id"]
        assert conv_id.startswith("conv_")
        assert start_data["persona"] == "worker"

        # Send message (mock LLM)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I can help with that."
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=20)

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            resp = await self.client.post("/agent/chat/message", json={
                "conversation_id": conv_id,
                "message": "Hello agent",
            })
            assert resp.status == 200

            # Read streamed ndjson
            body = await resp.text()
            events = [json.loads(line) for line in body.strip().split("\n") if line.strip()]
            types = [e["type"] for e in events]
            assert "text_delta" in types
            assert "done" in types

            # Verify content
            text_events = [e for e in events if e["type"] == "text_delta"]
            assert any("help" in e.get("content", "") for e in text_events)

            # Verify usage in done event
            done_events = [e for e in events if e["type"] == "done"]
            assert len(done_events) == 1
            assert "usage" in done_events[0]
            assert done_events[0]["usage"]["input_tokens"] == 50

        # Stop
        resp = await self.client.post("/agent/chat/stop", json={"conversation_id": conv_id})
        assert resp.status == 200
        stop_data = await resp.json()
        assert stop_data["stopped"] is True

        # Verify conversation is gone
        resp = await self.client.post("/agent/chat/stop", json={"conversation_id": conv_id})
        assert resp.status == 404

    async def test_message_to_nonexistent_conversation(self):
        """Sending to a bad conversation_id returns 404."""
        resp = await self.client.post("/agent/chat/message", json={
            "conversation_id": "conv_doesnotexist",
            "message": "hello",
        })
        assert resp.status == 404

    async def test_personas_endpoint(self):
        """Verify personas endpoint returns valid data."""
        resp = await self.client.get("/agent/chat/personas")
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Each persona should have required fields
        for persona in data:
            assert "persona" in persona
            assert "label" in persona
            assert "color" in persona
