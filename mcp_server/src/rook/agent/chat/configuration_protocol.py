"""Closed configuration-v1 wire shapes; Prime owns provider semantics and storage."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

INPUT_RECORD = 256 * 1024
INPUT_TOTAL = 512 * 1024
INPUT_COUNT = 64
OUTPUT_RECORD = 2 * 1024 * 1024
OUTPUT_TOTAL = 4 * 1024 * 1024
OUTPUT_COUNT = 256
STDERR_TOTAL = 64 * 1024
READ_OPERATIONS = frozenset({"status", "models", "endpoint.read"})
OPERATIONS = READ_OPERATIONS | {"oauth.connect", "oauth.disconnect", "apiKey.set", "apiKey.remove", "endpoint.save", "defaults.save"}
CODES = frozenset({"ok", "invalid_request", "unsupported_configuration", "unsupported_choice", "authentication_failed",
                   "storage_failed", "cancelled", "deadline_exceeded", "bounds_exceeded", "internal_error"})


class ConfigurationError(ValueError):
    def __init__(self, code: str = "invalid_request") -> None:
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str = "invalid_request") -> None:
    if not condition:
        raise ConfigurationError(code)


def _object(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    require(type(value) is dict and required <= value.keys() and value.keys() <= required | optional)


def _text(value: Any, limit: int = 256, *, empty: bool = False) -> None:
    require(type(value) is str and (empty or bool(value)) and "\0" not in value)
    try:
        require(len(value.encode("utf-8", errors="strict")) <= limit, "bounds_exceeded")
    except UnicodeError:
        raise ConfigurationError() from None


def _array(value: Any, limit: int) -> None:
    require(type(value) is list)
    require(len(value) <= limit, "bounds_exceeded")


def _strings(value: Any, limit: int, size: int = 256) -> None:
    _array(value, limit)
    for item in value:
        _text(item, size)
    require(len(value) == len(set(value)))


def _unicode(value: Any) -> None:
    if isinstance(value, str):
        _text(value, OUTPUT_RECORD, empty=True)
    elif isinstance(value, dict):
        for key, item in value.items():
            _unicode(key)
            _unicode(item)
    elif isinstance(value, list):
        for item in value:
            _unicode(item)
    elif isinstance(value, float):
        require(math.isfinite(value))


def parse_record(raw: bytes, limit: int = INPUT_RECORD) -> dict:
    require(len(raw) <= limit, "bounds_exceeded")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
        require(type(value) is dict)
        _unicode(value)
        return value
    except ConfigurationError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise ConfigurationError() from None


def encode_record(value: dict, limit: int) -> bytes:
    try:
        _unicode(value)
        raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
    except (ValueError, UnicodeError, RecursionError):
        raise ConfigurationError() from None
    require(len(raw) <= limit, "bounds_exceeded")
    return raw


def _envelope(value: dict, kind: str, fields: set[str], optional: set[str] = frozenset()) -> None:
    _object(value, {"v", "type", "operationId"} | fields, optional)
    require(type(value["v"]) is int and value["v"] == 1 and value["type"] == kind)
    require(type(value["operationId"]) is str and re.fullmatch(r"[a-f0-9]{32}", value["operationId"]) is not None)


def _model_input(value: Any) -> None:
    _strings(value, 2)
    require(bool(value) and set(value) <= {"text", "image"})


def _editable_models(value: Any) -> None:
    _array(value, 64)
    for model in value:
        _object(model, {"id", "name", "reasoning", "input", "contextWindow", "maxTokens"})
        _text(model["id"])
        _text(model["name"], 512)
        require(type(model["reasoning"]) is bool)
        _model_input(model["input"])
        for key in ("contextWindow", "maxTokens"):
            require(type(model[key]) is int and 0 < model[key] <= 2**53 - 1)


def _compat(value: Any) -> None:
    _object(value, set(), {"supportsDeveloperRole", "supportsReasoningEffort"})
    require(all(type(item) is bool for item in value.values()))


def _endpoint(value: Any, *, reading: bool) -> None:
    fields = {"baseUrl", "api", "authHeader", "models"}
    _object(value, fields | ({"headerNames", "compat"} if reading else {"provider", "headers"}),
            set() if reading else {"compat"})
    _text(value["baseUrl"], 4096)
    _text(value["api"])
    require(type(value["authHeader"]) is bool)
    _editable_models(value["models"])
    if "compat" in value:
        _compat(value["compat"])
    if reading:
        _strings(value["headerNames"], 32)
    else:
        headers = value["headers"]
        _object(headers, {"action"}, {"values"})
        require(headers["action"] in ("keep", "replace"))
        if headers["action"] == "keep":
            _object(headers, {"action"})
        else:
            _object(headers, {"action", "values"})
            require(type(headers["values"]) is dict)
            require(len(headers["values"]) <= 32, "bounds_exceeded")
            for name, secret in headers["values"].items():
                _text(name)
                _text(secret, 8192, empty=True)


@dataclass(frozen=True)
class ConfigurationBegin:
    operation_id: str
    operation: str
    input: dict = field(repr=False)

    def wire(self) -> dict:
        return {"v": 1, "type": "begin", "operationId": self.operation_id, "operation": self.operation, "input": self.input}


def validate_begin(value: dict) -> ConfigurationBegin:
    _envelope(value, "begin", {"operation", "input"})
    require(type(value["operation"]) is str and value["operation"] in OPERATIONS)
    operation, data = value["operation"], value["input"]
    if operation == "status":
        _object(data, set())
    else:
        fields = {"provider"}
        if operation == "apiKey.set":
            fields |= {"key"}
        elif operation == "defaults.save":
            fields |= {"model", "reasoning"}
        elif operation == "endpoint.save":
            fields |= {"baseUrl", "api", "authHeader", "headers", "models"}
        _object(data, fields, {"compat"} if operation == "endpoint.save" else set())
        _text(data["provider"])
        if operation == "apiKey.set":
            _text(data["key"], 16384)
        elif operation == "defaults.save":
            _text(data["model"])
            _text(data["reasoning"])
        elif operation == "endpoint.save":
            _endpoint(data, reading=False)
    encode_record(value, INPUT_RECORD)
    return ConfigurationBegin(value["operationId"], operation, data)


def validate_control(value: dict, kind: str) -> dict:
    _envelope(value, kind, {"requestId", "value"} if kind == "reply" else set())
    if kind == "reply":
        require(type(value["requestId"]) is int and 0 < value["requestId"] <= 2**53 - 1)
        _text(value["value"], 16384, empty=True)
    encode_record(value, INPUT_RECORD)
    return value


@dataclass(frozen=True)
class ConfigurationResult:
    operation_id: str
    outcome: str
    persistence: str
    code: str
    data: dict | None = field(default=None, repr=False)

    def wire(self) -> dict:
        return {"v": 1, "type": "result", "operationId": self.operation_id, "outcome": self.outcome,
                "persistence": self.persistence, "code": self.code, **({"data": self.data} if self.data is not None else {})}


def _result_data(data: Any, begin: ConfigurationBegin) -> None:
    if begin.operation == "status":
        _object(data, {"providers", "defaults", "apis"})
        _strings(data["apis"], 64)
        _object(data["defaults"], {"provider", "model", "reasoning"})
        for item in data["defaults"].values():
            if item is not None:
                _text(item)
        _array(data["providers"], 256)
        for provider in data["providers"]:
            _object(provider, {"id", "name", "methods", "credentialType", "configured", "route", "headerNames"}, {"endpoint"})
            _text(provider["id"])
            _text(provider["name"], 512)
            _strings(provider["methods"], len(OPERATIONS))
            require(set(provider["methods"]) <= OPERATIONS)
            require(provider["credentialType"] in ("none", "oauth", "api_key") and
                    provider["route"] in ("dedicated", "local_no_account", "none") and type(provider["configured"]) is bool)
            _strings(provider["headerNames"], 32)
            if "endpoint" in provider:
                _text(provider["endpoint"], 4096)
    elif begin.operation == "models":
        _object(data, {"provider", "models", "access"})
        require(data["provider"] == begin.input["provider"] and data["access"] == "unverified")
        _array(data["models"], 512)
        for model in data["models"]:
            _object(model, {"id", "name", "input", "reasoningLevels"})
            _text(model["id"])
            _text(model["name"], 512)
            _model_input(model["input"])
            _strings(model["reasoningLevels"], 64)
    elif begin.operation == "endpoint.read":
        _object(data, {"provider", "entry"})
        require(data["provider"] == begin.input["provider"])
        if data["entry"] is not None:
            _endpoint(data["entry"], reading=True)
    else:
        raise ConfigurationError()


def validate_event(value: dict, begin: ConfigurationBegin) -> dict:
    kind = value.get("type")
    if kind == "progress":
        _envelope(value, kind, {"stage"})
        require(value["stage"] in ("loading", "authorizing", "awaiting_input", "validating", "saving", "reading_back"))
    elif kind == "authorize":
        _envelope(value, kind, {"url", "instructionCode"}, {"instructions"})
        require(begin.operation == "oauth.connect" and value["instructionCode"] == "open_browser")
        _text(value["url"], 8192)
        try:
            url = urlsplit(value["url"])
            require(url.scheme in {"http", "https"} and bool(url.hostname) and url.username is None and url.password is None)
        except ValueError:
            raise ConfigurationError() from None
        if "instructions" in value:
            _text(value["instructions"], 8192, empty=True)
    elif kind == "input":
        _envelope(value, kind, {"requestId", "kind", "label", "secret"}, {"choices"})
        require(begin.operation == "oauth.connect" and type(value["requestId"]) is int and 0 < value["requestId"] <= 2**53 - 1)
        require(value["kind"] in ("text", "code", "select") and type(value["secret"]) is bool)
        _text(value["label"], 512)
        if value["kind"] == "select":
            _array(value.get("choices"), 32)
            require(bool(value["choices"]))
            for choice in value["choices"]:
                _object(choice, {"id", "label"})
                _text(choice["id"])
                _text(choice["label"], 512)
            require(len({choice["id"] for choice in value["choices"]}) == len(value["choices"]))
        else:
            require("choices" not in value)
    elif kind == "result":
        _envelope(value, kind, {"outcome", "persistence", "code"}, {"data"})
        require(value["outcome"] in ("completed", "cancelled", "failed") and
                value["persistence"] in ("not_applicable", "unchanged", "saved", "unknown") and
                type(value["code"]) is str and value["code"] in CODES)
        if value["outcome"] == "completed" and begin.operation in READ_OPERATIONS:
            _result_data(value.get("data"), begin)
        else:
            require("data" not in value)
    else:
        raise ConfigurationError()
    require(value["operationId"] == begin.operation_id)
    return value
