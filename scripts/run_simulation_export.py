"""Live gate driver (Task 6): render the Pearson mullion band-peel wave via the
per-member simulation export, then assemble the video. Requires Rhino open with
Pearson active + saved and the animation canvas loaded (C42 emits samples on H).
"""
import sys, asyncio, uuid, json, os, time, hashlib, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server" / "src"))
import httpx
from rook.bridge import get_rhino_host
from rook import director_simulation_export as sx
from rook import director_video

SCRATCH = Path(os.environ.get("ROOK_SIM_EXPORT_SCRATCH") or Path(tempfile.gettempdir()) / "rook-sim-export" / "sim_take")
FRAME_COUNT = int(os.environ.get("SIM_FRAMES", "48"))
HARVEST_CACHE_DIR = Path(SCRATCH) / "harvest_cache"


def harvest_cache_signature(doc_path, args, canvas_hash):
    payload = {
        "cache_version": 1,
        "doc_path": doc_path,
        "actor_set_id": args["actor_set_id"],
        "block_name": args["block_name"],
        "source_top_level_object_id": args["source_top_level_object_id"],
        "frame_count": args["frame_count"],
        "clock_denominator": args["clock_denominator"],
        "canvas_hash": canvas_hash,
    }
    return hashlib.sha256(sx.canonical_json_text(payload).encode("utf-8")).hexdigest()


def harvest_cache_path(signature):
    return HARVEST_CACHE_DIR / f"{signature}.json"


def load_harvest_cache(path, signature):
    path = Path(path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("signature") != signature:
        return None
    harvest = payload.get("harvest")
    return harvest if isinstance(harvest, dict) else None


def _sha256_json(payload):
    return hashlib.sha256(sx.canonical_json_text(payload).encode("utf-8")).hexdigest()


def harvest_cache_reuse_enabled(environ=os.environ):
    return environ.get("SIM_REUSE_HARVEST") == "1"


async def call_native(endpoint, method="GET", data=None, *, port=None):
    async def _send_once():
        base = get_rhino_host()
        if not base:
            raise RuntimeError("No active Rhino host found")
        async with httpx.AsyncClient(timeout=3600.0) as c:  # 1h: heavy SOH capture must not client-timeout
            resp = (await c.get(f"{base}{endpoint}", params=data or None) if method == "GET"
                    else await c.post(f"{base}{endpoint}", json=data or {}))
        return resp.json()

    try:
        return await _send_once()
    except httpx.ConnectError:
        return await _send_once()


async def main():
    print("HOST:", get_rhino_host(), "| frames:", FRAME_COUNT, flush=True)
    doc = (await call_native("/document", "GET"))["data"]
    print("Rhino doc:", doc.get("path"), "| modified:", doc.get("modified"), flush=True)
    args = {
        "take_id": f"sim_{uuid.uuid4().hex[:6]}",
        "actor_set_id": "actor_a28cbdb551fa",
        "block_name": "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL",
        "source_top_level_object_id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
        "output_root": SCRATCH,
        "frame_count": FRAME_COUNT, "fps": 24, "units": doc.get("units", "millimeters"),
        "clock_denominator": 240,
        # SOH-Rendered-2_NO EDGES by NAME — package_take validates display_modes by
        # name (director_take_package.py:215), not id, so the UUID reads as "missing".
        "display_modes": ["SOH-Rendered-2_NO EDGES"],
        "capture_mode": "SOH-Rendered-2_NO EDGES",
        "resolution": {"width": 1280, "height": 720},
    }
    canvas_state = (await call_native("/gh/query", "GET"))["data"]
    canvas_hash = _sha256_json(canvas_state)
    cache_sig = harvest_cache_signature(doc.get("path"), args, canvas_hash)
    cache_path = harvest_cache_path(cache_sig)
    reuse_harvest = harvest_cache_reuse_enabled()
    cached_harvest = load_harvest_cache(cache_path, cache_sig) if reuse_harvest else None
    if cached_harvest:
        args["precomputed_harvest"] = cached_harvest
        print("HARVEST CACHE HIT:", cache_path, flush=True)
    else:
        args["harvest_cache_path"] = str(cache_path)
        args["harvest_cache_signature"] = cache_sig
        mode = "MISS" if reuse_harvest else "REFRESH (set SIM_REUSE_HARVEST=1 to reuse)"
        print("HARVEST CACHE", mode + ":", cache_path, flush=True)
    t0 = time.time()
    result = await sx.run_simulation_export(args, call_native=call_native)
    print("PIPELINE OK in %.1fs | prepared=%s compiled=%s | artifact frames=%d ids=%d"
          % (time.time() - t0, result["prepared"], result["compiled"],
             result["artifact"]["frame_count"], len(result["artifact"]["ids"])), flush=True)
    cap = result["capture"]
    run_root = cap["run_root"]
    print("CAPTURED:", cap.get("frames_written"), "frames | run_root:", run_root, flush=True)

    aenv = await director_video.assemble_director_video({"run_root": run_root}, call_native=call_native)
    out = aenv.get("output_path") or ""
    abs_out = out if os.path.isabs(out) else os.path.join(run_root, out)  # assemble returns a run-relative path
    ok = aenv.get("state") == "complete" and not aenv.get("error")
    print("ASSEMBLE:", "OK" if ok else "FAIL", "| video:", abs_out, flush=True)
    if ok and os.path.exists(abs_out):
        print("=== VIDEO READY === bytes:", os.path.getsize(abs_out), flush=True)
    else:
        print("VIDEO MISSING — assemble env:", json.dumps(aenv)[:600], flush=True)

    after = (await call_native("/document", "GET"))["data"]
    print("Rhino doc restored:", after.get("path"), "| modified:", after.get("modified"), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
