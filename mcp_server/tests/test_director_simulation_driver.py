import asyncio
import importlib.util
from pathlib import Path

import httpx


def _load_driver():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_simulation_export.py"
    spec = importlib.util.spec_from_file_location("run_simulation_export_driver", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_call_native_re_resolves_host_and_retries_once_on_connect_error(monkeypatch):
    driver = _load_driver()
    hosts = iter(["http://old-port", "http://new-port"])
    attempts = []

    class FakeResponse:
        def json(self):
            return {"success": True, "data": {"ok": True}}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            attempts.append((url, params))
            if url.startswith("http://old-port"):
                raise httpx.ConnectError("dead port")
            return FakeResponse()

        async def post(self, url, json=None):
            raise AssertionError("GET test should not POST")

    monkeypatch.setattr(driver, "get_rhino_host", lambda: next(hosts))
    monkeypatch.setattr(driver.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(driver.call_native("/document", "GET", {"x": "1"}))

    assert result == {"success": True, "data": {"ok": True}}
    assert attempts == [
        ("http://old-port/document", {"x": "1"}),
        ("http://new-port/document", {"x": "1"}),
    ]
