from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_DISCOVERY_DIR = Path(tempfile.gettempdir()) / "rook"


class DiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class OwnedRhinoRecord:
    pid: int
    host: str
    port: int
    path: Path
    raw: dict[str, Any]


class OwnedRhinoDiscovery:
    def __init__(self, discovery_dir: Path = DEFAULT_DISCOVERY_DIR):
        self.discovery_dir = discovery_dir

    def owned_path(self, pid: int) -> Path:
        return self.discovery_dir / f"instance-{pid}-native.json"

    def read_owned_record(self, pid: int) -> OwnedRhinoRecord:
        path = self.owned_path(pid)
        if not path.exists():
            raise DiscoveryError(f"owned Rhino discovery file not found: {path}")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DiscoveryError(f"malformed JSON in owned Rhino discovery file: {path}") from exc

        process_id = raw.get("processId")
        if process_id != pid:
            raise DiscoveryError(f"wrong processId in owned Rhino discovery file: {process_id}")

        plugin_type = raw.get("pluginType")
        if plugin_type != "native":
            raise DiscoveryError(f"unexpected pluginType in owned Rhino discovery file: {plugin_type}")

        host = (raw.get("host") or "127.0.0.1").strip().lower()
        if host not in LOOPBACK_HOSTS:
            raise DiscoveryError(f"owned Rhino discovery host must be loopback: {host}")

        port = raw.get("port")
        if not isinstance(port, int) or port <= 0:
            raise DiscoveryError(f"invalid port in owned Rhino discovery file: {port}")

        return OwnedRhinoRecord(pid=pid, host=host, port=port, path=path, raw=raw)

    def snapshot_owned_record(self, record: OwnedRhinoRecord, artifact_dir: Path) -> Path:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = artifact_dir / f"owned-discovery-{record.path.name}"
        snapshot_path.write_text(json.dumps(record.raw, indent=2), encoding="utf-8")
        return snapshot_path
