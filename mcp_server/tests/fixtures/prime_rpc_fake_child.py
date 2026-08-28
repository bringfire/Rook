from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def emit(value: object) -> None:
    encoded = json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--mode")
parser.add_argument("--session-dir", required=True)
parser.add_argument("--no-tools", action="store_true")
parser.add_argument("--no-extensions", action="store_true")
parser.add_argument("--no-skills", action="store_true")
parser.add_argument("--no-context-files", action="store_true")
parser.add_argument("--no-prompt-templates", action="store_true")
parser.add_argument("--model")
parser.add_argument("--thinking")
parser.add_argument("--resume")
parser.add_argument("--scenario", default="complete")
parser.add_argument("--environment-output")
args, _unknown = parser.parse_known_args()

if args.environment_output:
    Path(args.environment_output).write_text(
        json.dumps(
            {
                key: value
                for key, value in __import__("os").environ.items()
                if key in {
                    "ANTHROPIC_API_KEY",
                    "OPENAI_API_KEY",
                    "SERPER_API_KEY",
                    "AWS_PROFILE",
                    "ROOK_SESSION_NONCE",
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

session_path = Path(args.resume or (Path(args.session_dir) / "fixture-session.jsonl"))
session_path.parent.mkdir(parents=True, exist_ok=True)
session_path.touch(exist_ok=True)
provider, model_id = (args.model or "fixture/model").split("/", 1)
thinking = args.thinking
pending_prompt_id: str | None = None
stalled_request_id: str | None = None

if args.scenario == "stderr_flood":
    sys.stderr.buffer.write(b"x" * (300 * 1024))
    sys.stderr.buffer.flush()


def state_response(request_id: str) -> None:
    emit(
        {
            "id": request_id,
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {
                "sessionId": "fixture-session",
                "sessionFile": str(session_path.absolute()),
                "model": {"provider": provider, "id": model_id},
                "thinkingLevel": thinking,
            },
        }
    )


def segment(number: int) -> None:
    emit({"type": "agent_start"})
    emit(
        {
            "type": "message_update",
            "message": {"role": "assistant", "content": []},
            "assistantMessageEvent": {
                "type": "text_delta",
                "contentIndex": 0,
                "delta": f"segment-{number}",
                "partial": {},
            },
        }
    )
    emit({"type": "agent_end", "messages": []})


for line in sys.stdin:
    command = json.loads(line)
    request_id = command["id"]
    command_type = command["type"]

    if command_type == "get_state":
        state_response(request_id)
        continue
    if command_type == "get_available_models":
        if args.scenario == "stalled_control_response":
            stalled_request_id = request_id
            continue
        emit(
            {
                "id": request_id,
                "type": "response",
                "command": command_type,
                "success": True,
                "data": {
                    "models": [
                        {
                            "provider": provider,
                            "id": model_id,
                            "contextWindow": 272000,
                            "reasoning": True,
                        }
                    ]
                },
            }
        )
        continue
    if command_type == "set_model":
        provider = command["provider"]
        model_id = command["modelId"]
        emit(
            {
                "id": request_id,
                "type": "response",
                "command": command_type,
                "success": True,
                "data": {"provider": provider, "id": model_id},
            }
        )
        continue
    if command_type == "set_thinking_level":
        thinking = command["level"]
        emit(
            {
                "id": request_id,
                "type": "response",
                "command": command_type,
                "success": True,
            }
        )
        continue
    if command_type == "prompt_and_wait":
        if args.scenario == "vertical_cancel_race":
            segment(1)
            segment(2)
            pending_prompt_id = request_id
            continue
        if args.scenario in {"prompt_pending_until_abort", "complete_before_abort_response"}:
            pending_prompt_id = request_id
            continue
        if args.scenario == "provider_failure":
            emit(
                {
                    "id": request_id,
                    "type": "response",
                    "command": command_type,
                    "success": False,
                    "error": {
                        "code": "execution_failed",
                        "message": "fixture provider failure",
                    },
                }
            )
            continue
        if args.scenario == "malformed_json":
            sys.stdout.buffer.write(b"{malformed\n")
            sys.stdout.buffer.flush()
            continue
        if args.scenario == "malformed_response":
            emit(
                {
                    "id": request_id,
                    "type": "response",
                    "command": command_type,
                    "success": "yes",
                }
            )
            continue
        if args.scenario == "wrong_response_id":
            emit(
                {
                    "id": "unknown-response",
                    "type": "response",
                    "command": command_type,
                    "success": True,
                    "data": {"outcome": "completed"},
                }
            )
            emit(
                {
                    "id": request_id,
                    "type": "response",
                    "command": "abort",
                    "success": True,
                }
            )
            continue
        if args.scenario == "exit_mid_prompt":
            sys.exit(7)
        if args.scenario == "oversized_row":
            emit({"type": "message_update", "blob": "x" * 1024})
            continue
        segment(1)
        if args.scenario == "two_segments_then_complete":
            segment(2)
        emit(
            {
                "id": request_id,
                "type": "response",
                "command": command_type,
                "success": True,
                "data": {"outcome": "completed"},
            }
        )
        if args.scenario == "duplicate_response":
            emit(
                {
                    "id": request_id,
                    "type": "response",
                    "command": command_type,
                    "success": True,
                    "data": {"outcome": "completed"},
                }
            )
        continue
    if command_type == "abort":
        if stalled_request_id is not None:
            emit(
                {
                    "id": stalled_request_id,
                    "type": "response",
                    "command": "get_available_models",
                    "success": True,
                    "data": {"models": []},
                }
            )
            stalled_request_id = None
        if pending_prompt_id is not None and args.scenario in {
            "complete_before_abort_response",
            "vertical_cancel_race",
        }:
            emit(
                {
                    "id": pending_prompt_id,
                    "type": "response",
                    "command": "prompt_and_wait",
                    "success": True,
                    "data": {"outcome": "completed"},
                }
            )
            pending_prompt_id = None
            time.sleep(0.02)
        emit(
            {
                "id": request_id,
                "type": "response",
                "command": command_type,
                "success": True,
            }
        )
        if pending_prompt_id is not None:
            emit(
                {
                    "id": pending_prompt_id,
                    "type": "response",
                    "command": "prompt_and_wait",
                    "success": True,
                    "data": {"outcome": "aborted"},
                }
            )
            pending_prompt_id = None
