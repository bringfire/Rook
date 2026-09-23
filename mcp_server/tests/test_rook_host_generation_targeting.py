from __future__ import annotations

import json
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
        lambda timeout=None, headers=None: _SequencedClient(calls, live_capabilities),
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
        lambda timeout=None, headers=None: _SequencedClient(
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


class _DestinationClient:
    def __init__(self, calls: list[tuple[str, int | None]]) -> None:
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params=None):
        parsed = urlparse(str(url))
        self._calls.append((parsed.path, parsed.port))
        if parsed.path == "/capabilities":
            return _Response({"domains": [], "hostGenerationId": HOST_GENERATION})
        return _Response({"success": True, "data": {"name": "bound.3dm"}})


class _CapabilityClient:
    def __init__(
        self,
        calls: list[tuple[str, int | None]],
        *,
        payload: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._calls = calls
        self._payload = payload
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url):
        parsed = urlparse(str(url))
        self._calls.append((parsed.path, parsed.port))
        if self._error is not None:
            raise self._error
        return _Response(self._payload or {})


@pytest.mark.asyncio
async def test_discovery_churn_cannot_split_verification_and_operation(monkeypatch) -> None:
    targeting.initialize_from_environment(_panel_environment())
    original = _instance()
    replacement = {**_instance(), "port": 9951}
    discovery_count = 0

    def changing_discovery():
        nonlocal discovery_count
        discovery_count += 1
        return [original] if discovery_count <= 2 else [replacement]

    monkeypatch.setattr(bridge, "discover_instances", changing_discovery)
    calls: list[tuple[str, int | None]] = []
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None, headers=None: _DestinationClient(calls),
    )

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is True
    assert calls == [("/capabilities", 9950), ("/document", 9950)]
    assert discovery_count == 1


@pytest.mark.asyncio
async def test_multiple_matching_panel_listeners_refuse_before_http(monkeypatch) -> None:
    targeting.initialize_from_environment(_panel_environment())
    instances = [_instance(), {**_instance(), "port": 9951}]
    monkeypatch.setattr(bridge, "discover_instances", lambda: instances)

    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("ambiguous panel authority must refuse before HTTP")

    monkeypatch.setattr(bridge.httpx, "AsyncClient", ForbiddenClient)

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is False
    assert result["data"]["error"] == "target_unavailable"


def test_production_discovery_preserves_distinct_panel_routes(tmp_path, monkeypatch) -> None:
    first = _instance()
    second = {**_instance(), "port": 9951}
    (tmp_path / "instance-1234-native-a.json").write_text(
        json.dumps(first), encoding="utf-8"
    )
    (tmp_path / "instance-1234-native-b.json").write_text(
        json.dumps(second), encoding="utf-8"
    )
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda process_id: True)

    instances = bridge.discover_instances()

    assert sorted(instance["port"] for instance in instances) == [9950, 9951]
    targeting.initialize_from_environment(_panel_environment())
    assert targeting.resolve_panel_target_instance(instances) is None


@pytest.mark.asyncio
async def test_forged_discovery_live_endpoint_cannot_change_verification_route(
    monkeypatch,
) -> None:
    targeting.initialize_from_environment(_panel_environment())
    instance = _instance()
    instance["capabilities"] = {"liveEndpoint": "/objects"}
    monkeypatch.setattr(bridge, "discover_instances", lambda: [instance])
    calls: list[tuple[str, int | None]] = []
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None, headers=None: _DestinationClient(calls),
    )

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is True
    assert calls == [("/capabilities", 9950), ("/document", 9950)]


@pytest.mark.asyncio
async def test_panel_locked_session_capabilities_refuses_alternate_session(
    monkeypatch,
) -> None:
    from rook import server

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment(_panel_environment())
    calls: list[object] = []

    async def forbidden_dispatch(session):
        calls.append(session)
        raise AssertionError("alternate session must be refused before dispatch")

    monkeypatch.setattr(server, "get_session_capabilities", forbidden_dispatch)

    result = await server.call_tool(
        "rhino_session_capabilities", {"session": "rhino-9999"}
    )

    assert "panel_target_locked" in result[0].text
    assert calls == []


@pytest.mark.asyncio
async def test_invalid_panel_authority_blocks_session_capabilities(monkeypatch) -> None:
    from rook import server

    invalid = _panel_environment()
    invalid.pop("ROOK_MCP_TARGET_HOST_GENERATION_ID")
    targeting.initialize_from_environment(invalid)
    calls: list[object] = []

    async def forbidden_dispatch(session):
        calls.append(session)
        raise AssertionError("invalid panel authority must refuse before dispatch")

    monkeypatch.setattr(server, "get_session_capabilities", forbidden_dispatch)

    result = await server.call_tool(
        "rhino_session_capabilities", {"session": "rhino-1234"}
    )

    assert "target_unavailable" in result[0].text
    assert calls == []


@pytest.mark.asyncio
async def test_panel_session_capabilities_uses_bound_discovery_generation(
    monkeypatch,
) -> None:
    targeting.initialize_from_environment(_panel_environment())
    wrong = _instance(OTHER_GENERATION)
    right = {**_instance(), "port": 9951}
    monkeypatch.setattr(bridge, "discover_instances", lambda: [wrong, right])
    monkeypatch.setattr(
        bridge,
        "classify_session_liveness",
        lambda instance: (_ for _ in ()).throw(
            AssertionError("panel capability authority must not use PID liveness")
        ),
    )
    calls: list[tuple[str, int | None]] = []
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None, headers=None: _CapabilityClient(
            calls,
            payload={"domains": [], "hostGenerationId": HOST_GENERATION},
        ),
    )

    result = await bridge.get_session_capabilities("rhino-1234")

    assert result["success"] is True
    assert result["data"]["capabilities"]["source"] == "live"
    assert calls == [("/capabilities", 9951)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "live_capabilities",
    [
        {"domains": []},
        {"domains": [], "hostGenerationId": OTHER_GENERATION},
    ],
)
async def test_panel_session_capabilities_requires_exact_live_generation(
    monkeypatch,
    live_capabilities: dict[str, object],
) -> None:
    targeting.initialize_from_environment(_panel_environment())
    monkeypatch.setattr(bridge, "discover_instances", lambda: [_instance()])
    monkeypatch.setattr(
        bridge,
        "classify_session_liveness",
        lambda instance: {"state": "live", "pidAlive": True, "portListening": True},
    )
    calls: list[tuple[str, int | None]] = []
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None, headers=None: _CapabilityClient(calls, payload=live_capabilities),
    )

    result = await bridge.get_session_capabilities("rhino-1234")

    assert result["success"] is False
    assert result["data"]["error"] == "target_unavailable"
    assert calls == [("/capabilities", 9950)]


@pytest.mark.asyncio
async def test_panel_session_capabilities_rejects_malformed_live_response(
    monkeypatch,
) -> None:
    targeting.initialize_from_environment(_panel_environment())
    monkeypatch.setattr(bridge, "discover_instances", lambda: [_instance()])
    monkeypatch.setattr(
        bridge,
        "classify_session_liveness",
        lambda instance: {"state": "live", "pidAlive": True, "portListening": True},
    )
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None, headers=None: _CapabilityClient(
            [], payload={"hostGenerationId": HOST_GENERATION}
        ),
    )

    result = await bridge.get_session_capabilities("rhino-1234")

    assert result["success"] is False
    assert result["data"]["error"] == "target_unavailable"


@pytest.mark.asyncio
async def test_panel_session_capabilities_transport_failure_never_uses_legacy_fallback(
    monkeypatch,
) -> None:
    targeting.initialize_from_environment(_panel_environment())
    monkeypatch.setattr(bridge, "discover_instances", lambda: [_instance()])
    liveness_calls: list[object] = []

    def classify(instance):
        liveness_calls.append(instance)
        return {"state": "live", "pidAlive": True, "portListening": True}

    monkeypatch.setattr(bridge, "classify_session_liveness", classify)
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None, headers=None: _CapabilityClient([], error=RuntimeError("offline")),
    )

    result = await bridge.get_session_capabilities("rhino-1234")

    assert result["success"] is False
    assert result["data"]["error"] == "target_unavailable"
    assert liveness_calls == []


@pytest.mark.asyncio
async def test_panel_session_capabilities_refuses_missing_bound_generation(
    monkeypatch,
) -> None:
    targeting.initialize_from_environment(_panel_environment())
    monkeypatch.setattr(bridge, "discover_instances", lambda: [_instance(OTHER_GENERATION)])

    def forbidden_pid_probe(process_id):
        raise AssertionError("panel authority must not degrade to PID liveness")

    monkeypatch.setattr(bridge, "_is_pid_alive", forbidden_pid_probe)

    result = await bridge.get_session_capabilities("rhino-1234")

    assert result["success"] is False
    assert result["data"]["error"] == "target_unavailable"
