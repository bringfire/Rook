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
        # Fail loudly rather than writing misleading evidence. A 400/404 means the
        # route is disabled/missing (flag not set, plugin not rebuilt); a false
        # envelope means the probe itself rejected the request.
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(f"ERROR: {strategy}: HTTP {r.status_code} — {r.text[:300]}")
            print("  (route disabled/missing? set ROOK_DIRECTOR_PUMPSPIKE=1 before "
                  "launching Rhino and redeploy the native build.)")
            sys.exit(1)

        envelope = r.json()
        if not envelope.get("success", False):
            print(f"ERROR: {strategy}: probe returned failure envelope: "
                  f"{json.dumps(envelope)[:300]}")
            sys.exit(1)

        data = envelope.get("data", {})
        results[strategy] = data
        print(strategy, json.dumps(data, indent=2))

    Path("pumpspike-evidence.json").write_text(json.dumps(results, indent=2))
    print("\nWritten: pumpspike-evidence.json")


if __name__ == "__main__":
    main()
