import json
from pathlib import Path

import httpx
import pytest

from rook.runtime_harness import DiscoveryError, OwnedRhinoDiscovery, ping_native


class FakeProcess:
    def __init__(self, pid: int, poll_results: list[int | None]):
        self.pid = pid
        self.returncode = None
        self._poll_results = poll_results

    def poll(self) -> int | None:
        if self._poll_results:
            self.returncode = self._poll_results.pop(0)
        return self.returncode


class PingRecorder:
    def __init__(self, results: list[bool]):
        self.results = results
        self.urls: list[tuple[str, int]] = []

    async def __call__(self, host: str, port: int) -> bool:
        self.urls.append((host, port))
        if self.results:
            return self.results.pop(0)
        return False


class FakeAsyncClient:
    response = httpx.Response(200, text="")
    urls: list[str] = []
    exception: Exception | None = None

    def __init__(self, timeout: float):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url: str):
        self.urls.append(url)
        if self.exception is not None:
            raise self.exception
        return self.response


def _write_record(discovery_dir: Path, pid: int, record: dict) -> Path:
    path = discovery_dir / f"instance-{pid}-native.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _native_record(pid: int, **overrides) -> dict:
    record = {
        "processId": pid,
        "pluginType": "native",
        "host": "127.0.0.1",
        "port": 9010,
    }
    record.update(overrides)
    return record


def test_owned_discovery_accepts_exact_native_pid(tmp_path: Path):
    pid = 1234
    path = _write_record(tmp_path, pid, _native_record(pid, host="LOCALHOST", port=9876))

    record = OwnedRhinoDiscovery(tmp_path).read_owned_record(pid)

    assert record.pid == pid
    assert record.host == "localhost"
    assert record.port == 9876
    assert record.path == path
    assert record.raw == _native_record(pid, host="LOCALHOST", port=9876)


def test_owned_discovery_accepts_whitespace_padded_loopback_host(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, host=" LOCALHOST "))

    record = OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)

    assert record.host == "localhost"


def test_owned_discovery_rejects_wrong_process_id(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(5678))

    with pytest.raises(DiscoveryError, match="wrong processId"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_boolean_process_id(tmp_path: Path):
    _write_record(tmp_path, 1, _native_record(True))

    with pytest.raises(DiscoveryError, match="processId"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1)


def test_owned_discovery_rejects_non_native_plugin_type(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, pluginType="managed"))

    with pytest.raises(DiscoveryError, match="pluginType"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


@pytest.mark.parametrize("port", [None, 0, -1, "abc", True])
def test_owned_discovery_rejects_invalid_port(tmp_path: Path, port):
    _write_record(tmp_path, 1234, _native_record(1234, port=port))

    with pytest.raises(DiscoveryError, match="port"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_missing_port(tmp_path: Path):
    record = _native_record(1234)
    del record["port"]
    _write_record(tmp_path, 1234, record)

    with pytest.raises(DiscoveryError, match="port"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "instance-1234-native.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="malformed JSON"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_top_level_non_object_json(tmp_path: Path):
    path = tmp_path / "instance-1234-native.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="object"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_non_loopback_host(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, host="192.168.1.10"))

    with pytest.raises(DiscoveryError, match="loopback"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_rejects_non_string_host(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, host=123))

    with pytest.raises(DiscoveryError, match="host|loopback"):
        OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)


def test_owned_discovery_snapshots_json(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    _write_record(tmp_path, 1234, _native_record(1234, host=""))
    record = OwnedRhinoDiscovery(tmp_path).read_owned_record(1234)

    snapshot_path = OwnedRhinoDiscovery(tmp_path).snapshot_owned_record(record, artifact_dir)

    assert snapshot_path == artifact_dir / "owned-discovery-instance-1234-native.json"
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == record.raw
    assert "\n  " in snapshot_path.read_text(encoding="utf-8")


def test_owned_discovery_never_reads_other_healthy_rhino(tmp_path: Path):
    _write_record(tmp_path, 1111, _native_record(1111, port=9011))
    discovery = OwnedRhinoDiscovery(tmp_path)

    with pytest.raises(DiscoveryError, match="not found"):
        discovery.read_owned_record(2222)


def test_wait_for_ready_reports_owned_process_exit_before_discovery(tmp_path: Path):
    pid = 1234
    process = FakeProcess(pid, [None, 17])
    ping = PingRecorder([True])

    with pytest.raises(
        DiscoveryError,
        match="Rhino exited with code 17 before RookNative discovery appeared",
    ):
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            pid,
            process,
            ping,
            timeout_seconds=1.0,
            poll_seconds=0,
        )

    assert ping.urls == []


def test_wait_for_ready_pings_exact_owned_port(tmp_path: Path):
    pid = 1234
    _write_record(tmp_path, pid, _native_record(pid, host="localhost", port=9821))
    ping = PingRecorder([False, True])

    record = OwnedRhinoDiscovery(tmp_path).wait_for_ready(
        pid,
        FakeProcess(pid, [None, None]),
        ping,
        timeout_seconds=1.0,
        poll_seconds=0,
    )

    assert record.pid == pid
    assert record.host == "localhost"
    assert record.port == 9821
    assert ping.urls == [("localhost", 9821), ("localhost", 9821)]


def test_wait_for_ready_times_out_when_ping_never_succeeds(tmp_path: Path):
    pid = 1234
    _write_record(tmp_path, pid, _native_record(pid, host="127.0.0.1", port=9821))
    ping = PingRecorder([False, False, False])

    with pytest.raises(DiscoveryError, match="did not become pingable"):
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            pid,
            FakeProcess(pid, [None, None, None]),
            ping,
            timeout_seconds=0.01,
            poll_seconds=0,
        )

    assert ping.urls
    assert set(ping.urls) == {("127.0.0.1", 9821)}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="pong"),
        httpx.Response(200, json={"data": "pong"}),
        httpx.Response(200, json={"success": True}),
    ],
)
async def test_ping_native_accepts_supported_pong_shapes(monkeypatch, response):
    FakeAsyncClient.response = response
    FakeAsyncClient.urls = []
    FakeAsyncClient.exception = None
    monkeypatch.setattr("rook.runtime_harness.httpx.AsyncClient", FakeAsyncClient)

    assert await ping_native("localhost", 9821) is True

    assert FakeAsyncClient.urls == ["http://localhost:9821/ping"]


@pytest.mark.asyncio
async def test_ping_native_returns_false_when_endpoint_not_listening(monkeypatch):
    FakeAsyncClient.urls = []
    FakeAsyncClient.exception = httpx.ConnectError("connection refused")
    monkeypatch.setattr("rook.runtime_harness.httpx.AsyncClient", FakeAsyncClient)

    assert await ping_native("localhost", 9821) is False

    assert FakeAsyncClient.urls == ["http://localhost:9821/ping"]
