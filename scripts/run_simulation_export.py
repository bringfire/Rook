"""Live gate driver (Task 6): render the Pearson mullion band-peel wave via the
per-member simulation export, then assemble the video. Requires Rhino open with
Pearson active + saved and the animation canvas loaded (C42 emits samples on H).
"""
import sys, asyncio, uuid, json, os, time
sys.path.insert(0, r"C:\Users\aryan\source\repos\Rook\.claude\worktrees\director-v3-sim-export\mcp_server\src")
import httpx
from rook.bridge import get_rhino_host
from rook import director_simulation_export as sx
from rook import director_video

BASE = get_rhino_host()
SCRATCH = (r"C:\Users\aryan\AppData\Local\Temp\claude\C--Users-aryan-source-repos-Rook"
           r"\51f4797b-8702-43db-9b2d-245df8501f2f\scratchpad\sim_take")
FRAME_COUNT = int(os.environ.get("SIM_FRAMES", "48"))


async def call_native(endpoint, method="GET", data=None, *, port=None):
    async with httpx.AsyncClient(timeout=1800.0) as c:
        resp = (await c.get(f"{BASE}{endpoint}", params=data or None) if method == "GET"
                else await c.post(f"{BASE}{endpoint}", json=data or {}))
    return resp.json()


async def main():
    print("HOST:", BASE, "| frames:", FRAME_COUNT, flush=True)
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
        "display_modes": ["Shaded"], "capture_mode": "Shaded",
        "resolution": {"width": 1280, "height": 720},
    }
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


asyncio.run(main())
