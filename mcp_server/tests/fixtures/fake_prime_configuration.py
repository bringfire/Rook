"""Synthetic pipe behavior only. No auth, network, persistence or provider imports."""

import json
import os
import sys
import time

assert sys.argv[1:] == ["configuration", "--stdio", "--configuration-policy", "rookchat"]
case = os.environ.get("ROOK_CONFIGURATION_TEST_CASE", "normal")
begin = json.loads(sys.stdin.buffer.readline())
envelope = {"v": 1, "operationId": begin["operationId"]}


def send(event_type, **fields):
    sys.stdout.buffer.write((json.dumps({**envelope, "type": event_type, **fields}) + "\n").encode())
    sys.stdout.buffer.flush()


if case == "invalid":
    sys.stdout.buffer.write(b'{"v":1,"v":1}\n')
    sys.stdout.buffer.flush()
elif case == "partial":
    sys.stdout.buffer.write(b'{"v":1')
    sys.stdout.buffer.flush()
elif case == "unicode":
    send("progress", stage="\ud800")
elif case == "frame-overflow":
    sys.stdout.buffer.write(b"x" * (2 * 1024 * 1024 + 1))
    sys.stdout.buffer.flush()
elif case == "stderr-overflow":
    sys.stderr.buffer.write(b"SYNTHETIC_PRIVATE_STDERR" * 4000)
    sys.stderr.buffer.flush()
elif case == "count-overflow":
    for _ in range(257):
        send("progress", stage="loading")
elif case == "no-result":
    pass
elif case == "deadline":
    time.sleep(600)
else:
    if case in {"oauth", "select", "double-input", "cancel-hang"}:
        send("authorize", url="https://example.invalid/authorize?state=SYNTHETIC_PRIVATE_URL",
             instructionCode="open_browser", instructions="SYNTHETIC_DEVICE_CODE")
        fields = {"requestId": 1, "kind": "select" if case == "select" else "code", "label": "Synthetic input", "secret": True}
        if case == "select":
            fields["choices"] = [{"id": "chosen", "label": "Choose this"}]
        send("input", **fields)
        if case == "double-input":
            send("input", **{**fields, "requestId": 2})
        control = json.loads(sys.stdin.buffer.readline())
        if case == "cancel-hang":
            time.sleep(600)
        if control["type"] == "cancel":
            send("result", outcome="cancelled", persistence="unchanged", code="cancelled")
            sys.exit(1)
        assert control["type"] == "reply" and control["requestId"] == 1
        assert control["value"] in {"SYNTHETIC_REPLY", "chosen"}
    if begin["operation"] == "status":
        send("result", outcome="completed", persistence="not_applicable", code="ok", data={
            "providers": [], "apis": ["openai-completions"],
            "defaults": {"provider": None, "model": None, "reasoning": None},
        })
    elif begin["operation"] == "models":
        send("result", outcome="completed", persistence="not_applicable", code="ok", data={
            "provider": begin["input"]["provider"], "models": [], "access": "unverified",
        })
    elif begin["operation"] == "endpoint.read":
        send("result", outcome="completed", persistence="not_applicable", code="ok", data={
            "provider": begin["input"]["provider"], "entry": {"api": "openai-completions",
            "baseUrl": "http://127.0.0.1:11434/v1", "authHeader": False, "headerNames": ["X-Example"],
            "models": [], "compat": {"supportsDeveloperRole": False}},
        })
    else:
        if begin["operation"] == "apiKey.set":
            assert begin["input"]["key"] == "SYNTHETIC_KEY_NAME"
        send("result", outcome="completed", persistence="saved", code="ok")
    if case == "saved-nonzero":
        sys.exit(9)
    if case == "saved-hang":
        time.sleep(600)
    if case == "saved-invalid":
        send("progress", stage="SYNTHETIC_PRIVATE_EXCEPTION")
