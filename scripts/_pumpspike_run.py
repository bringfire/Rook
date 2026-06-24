"""THROWAWAY pump-spike runner. Removed in Task 5. Discovers the native port
via bridge.py and POSTs /director/_pumpspike for each strategy."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server" / "src"))
from rook.bridge import discover_instances  # type: ignore
import httpx


def main():
    instances = discover_instances()
    native = next((i for i in instances if i.get("pluginType") == "native"), None)
    if not native:
        print("ERROR: no native Rook instance found — is Rhino running with the plugin loaded?")
        sys.exit(1)

    port = native["port"]
    print(f"Using native instance at port {port}")

    results = {}
    for strategy in ("S0_control", "S1_filtered", "S2_guarded"):
        r = httpx.post(
            f"http://127.0.0.1:{port}/director/_pumpspike",
            json={"strategy": strategy, "pump_ms": 500},
            timeout=30,
        )
        results[strategy] = r.json()
        print(strategy, json.dumps(results[strategy], indent=2))

    Path("pumpspike-evidence.json").write_text(json.dumps(results, indent=2))
    print("\nWritten: pumpspike-evidence.json")


if __name__ == "__main__":
    main()
