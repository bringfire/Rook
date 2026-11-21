"""Generic installed MCP stdio capture. Default permits discovery/status/estimation only.
Run with a dependency-equipped client interpreter; --python identifies the installed server.
Requests are data: {"calls":[{"name":"rhino_image_models","arguments":{}}]}.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

READ_ONLY = frozenset({"rhino_ping", "rhino_document", "rhino_image_models", "rhino_video_models", "rhino_image_estimate", "rhino_video_estimate", "rhino_image_status", "rhino_video_status", "rhino_image_result", "rhino_video_result", "rhino_image_jobs", "rhino_video_jobs"})

def sanitize(value):
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not any(token in k.lower() for token in ("api_key", "authorization", "credential", "base64"))}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str) and value.lower().startswith(("data:", "https://", "http://")):
        return {"redacted_sha256": hashlib.sha256(value.encode()).hexdigest()}
    return value

def admit(calls):
    if not calls or any(c.get("name") not in READ_ONLY or not isinstance(c.get("arguments"), dict) for c in calls):
        raise ValueError("Only explicit no-cost discovery, estimate and job reads are admitted by this capture program.")

async def capture(args):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    calls = json.loads(Path(args.requests).read_text(encoding="utf-8-sig"))["calls"]
    admit(calls)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["ROOK_MCP_TOOL_PROFILE"] = "full"
    probe = subprocess.run([args.python, "-I", "-c", "import sys,rook,json; print(json.dumps({'python':sys.executable,'prefix':sys.prefix,'rook':rook.__file__}))"], env=env, capture_output=True, text=True, check=True)
    origin = json.loads(probe.stdout)
    package = Path(origin["rook"]).resolve()
    installed = Path(origin["prefix"]).resolve() / "Lib" / "site-packages"
    if not package.is_relative_to(installed):
        raise ValueError("Server is not loading the installed wheel from its private site-packages.")
    report = {"schema_version": 1, "surface": "mcp", "origin": origin, "python_sha256": hashlib.sha256(Path(args.python).read_bytes()).hexdigest(), "calls": []}
    target = Path(args.report).resolve(); target.parent.mkdir(parents=True, exist_ok=True)
    with target.with_suffix(".stderr.log").open("w", encoding="utf-8") as errlog:
        params = StdioServerParameters(command=str(Path(args.python).resolve()), args=["-I", "-m", "rook"], env=env, cwd=str(installed),)
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), 60)
                inventory = await asyncio.wait_for(session.list_tools(), 60)
                report["inventory"] = [{"name": t.name, "input_schema": t.inputSchema} for t in inventory.tools]
                for call in calls:
                    result = await asyncio.wait_for(session.call_tool("rook_tools_call", {"name": call["name"], "arguments": call["arguments"]}), 60)
                    decoded=[]
                    for item in result.content:
                        if getattr(item, "type", None)=="text":
                            try: decoded.append(json.loads(item.text))
                            except ValueError: decoded.append(item.text)
                    report["calls"].append({"name":call["name"],"arguments":sanitize(call["arguments"]),"request_sha256":hashlib.sha256(json.dumps(call["arguments"],sort_keys=True,separators=(",", ":")).encode()).hexdigest(),"is_error":bool(result.isError),"result":sanitize(decoded)})
    target.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True); parser.add_argument("--requests", required=True); parser.add_argument("--report", required=True)
    asyncio.run(capture(parser.parse_args()))
