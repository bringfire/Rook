from __future__ import annotations

from urllib.parse import urlparse

import pytest

from rook import bridge, targeting


HOST_GENERATION = "11111111-1111-1111-1111-111111111111"
OTHER_GENERATION = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _reset_targeting() -> None:
    targeting.reset_targeting_state_for_tests()
    yield
    targeting.reset_targeting_state_for_tests()


def _panel_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION,
        "ROOK_MCP_TARGET_PROCESS_ID": "1234",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "55",
    }
    environment.update(overrides)
    return environment


def _instance(host_generation_id: object = HOST_GENERATION) -> dict[str, object]:
    return {
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 1234,
        "pluginType": "native",
        "hostGenerationId": host_generation_id,
        "capabilities": {"liveEndpoint": "/capabilities"},
    }


@pytest.mark.parametrize(
    "environment",
    [
        {
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_PROCESS_ID": "1234",
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "55",
        },
        _panel_environment(ROOK_MCP_TARGET_HOST_GENERATION_ID="not-a-uuid"),
        {
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION,
            "ROOK_MCP_TARGET_PROCESS_ID": "1234",
        },
    ],
)
def test_panel_lock_requires_complete_canonical_authority(environment: dict[str, str]) -> None:
    targeting.initialize_from_environment(environment)

    assert targeting.get_panel_target_lock() is None
    error = targeting.get_panel_target_config_error()
    assert error is not None
    assert error["error"] == "target_unavailable"


def test_panel_lock_retains_generation_pid_and_document_authority() -> None:
    targeting.initialize_from_environment(_panel_environment())

    lock = targeting.get_panel_target_lock()
    assert lock is not None
    assert lock.host_generation_id == HOST_GENERATION
    assert lock.process_id == 1234
    assert lock.document_serial_number == 55


@pytest.mark.asyncio
async def test_same_pid_wrong_discovery_generation_refuses_before_http(monkeypatch) -> None:
    targeting.initialize_from_environment(_panel_environment())
    instances = [_instance(OTHER_GENERATION)]
    monkeypatch.setattr(targeting, "discover_instances", lambda: instances)
    monkeypatch.setattr(bridge, "discover_instances", lambda: instances)

    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("HTTP must not start for a mismatched discovery generation")

    monkeypatch.setattr(bridge.httpx, "AsyncClient", ForbiddenClient)

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is False
    assert result["data"]["error"] == "target_unavailable"


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _SequencedClient:
    def __init__(
        self,
        calls: list[tuple[str, object]],
        live_capabilities: dict[str, object],
    ) -> None:
        self._calls = calls
        self._live_capabilities = live_capabilities

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params=None):
        path = urlparse(str(url)).path
        self._calls.append((path, params))
        if path == "/capabilities":
            return _Response(self._live_capabilities)
        return _Response({"success": True, "data": {"name": "bound.3dm"}})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "live_capabilities",
    [
        {"domains": []},
        {"domains": [], "hostGenerationId": "not-a-uuid"},
        {"domains": [], "hostGenerationId": OTHER_GENERATION},
    ],
)
async def test_live_generation_refusal_precedes_requested_operation(
    monkeypatch,
    live_capabilities: dict[str, object],
) -> None:
    targeting.initialize_from_environment(_panel_environment())
    instances = [_instance()]
    monkeypatch.setattr(targeting, "discover_instances", lambda: instances)
    monkeypatch.setattr(bridge, "discover_instances", lambda: instances)
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None: _SequencedClient(calls, live_capabilities),
    )

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is False
    assert result["data"]["error"] == "target_unavailable"
    assert calls == [("/capabilities", None)]


@pytest.mark.asyncio
async def test_matching_live_generation_dispatches_with_locked_document(monkeypatch) -> None:
    targeting.initialize_from_environment(_panel_environment())
    instances = [_instance()]
    monkeypatch.setattr(targeting, "discover_instances", lambda: instances)
    monkeypatch.setattr(bridge, "discover_instances", lambda: instances)
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None: _SequencedClient(
            calls,
            {"domains": [], "hostGenerationId": HOST_GENERATION},
        ),
    )

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is True
    assert calls == [
        ("/capabilities", None),
        ("/document", {"documentSerialNumber": "55"}),
    ]
