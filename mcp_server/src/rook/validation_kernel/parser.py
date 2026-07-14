"""Bounded byte tokenizer and iterative parser for owned JSON values."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .budget import BudgetLedger
from .canonical_json import canonical_fingerprint_metered, sha256_prefixed
from .control import ArtifactRole, BudgetDimension
from .owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    JsonValue,
    _seal_object_members,
)


_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_WHITESPACE = frozenset((0x20, 0x09, 0x0A, 0x0D))
_TOKEN_BOUNDARIES = _WHITESPACE | frozenset(b"[]{},:")
_PARSE_ARTIFACT_ROLES = frozenset(
    (ArtifactRole.RECIPE.value, ArtifactRole.VALIDATION_BUNDLE.value)
)
_AGGREGATE_DIMENSIONS = frozenset(
    (
        BudgetDimension.PARSED_NODES,
        BudgetDimension.DECODED_STRING_BYTES,
        BudgetDimension.PARSER_WORK_UNITS,
    )
)
_OWNED_VALUE_TYPES = (
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
)
_CATEGORY_MESSAGES = {
    "bom_not_allowed": "JSON input must not contain a UTF-8 BOM.",
    "duplicate_member": "JSON object member names must be unique.",
    "invalid_escape": "JSON string escape is invalid.",
    "invalid_number": "JSON number token is invalid.",
    "invalid_surrogate": "JSON string contains an invalid surrogate sequence.",
    "invalid_syntax": "JSON syntax is invalid.",
    "invalid_utf8": "JSON input is not valid UTF-8.",
    "nonfinite_number": "JSON number is outside the finite binary64 domain.",
}
_SIMPLE_ESCAPES = {
    0x22: 0x22,
    0x5C: 0x5C,
    0x2F: 0x2F,
    0x62: 0x08,
    0x66: 0x0C,
    0x6E: 0x0A,
    0x72: 0x0D,
    0x74: 0x09,
}


@dataclass(frozen=True, slots=True)
class ParsedJsonValue:
    """One immutable parsed value and its canonical value identity."""

    value: JsonValue
    value_fingerprint: str

    def __post_init__(self) -> None:
        if type(self.value) not in _OWNED_VALUE_TYPES:
            raise TypeError("parsed JSON value must be an exact owned value")
        if (
            type(self.value_fingerprint) is not str
            or not _SHA256_PATTERN.fullmatch(self.value_fingerprint)
        ):
            raise ValueError("parsed JSON fingerprint must be lowercase prefixed SHA-256")


@dataclass(frozen=True, slots=True)
class JsonParseEvidence:
    """Bounded internal evidence for one local parse rejection."""

    artifact_role: str
    category: str
    subject_path: str | None
    bounded_message: str
    detail_sha256: str

    def __post_init__(self) -> None:
        if type(self.artifact_role) is not str or self.artifact_role not in _PARSE_ARTIFACT_ROLES:
            raise ValueError("invalid parser artifact role")
        if type(self.category) is not str or self.category not in _CATEGORY_MESSAGES:
            raise ValueError("invalid parser evidence category")
        if self.subject_path is not None:
            if (
                type(self.subject_path) is not str
                or not self.subject_path.startswith("/")
                or len(self.subject_path) > 512
            ):
                raise ValueError("invalid bounded parser subject path")
        if (
            type(self.bounded_message) is not str
            or self.bounded_message != _CATEGORY_MESSAGES[self.category]
            or len(self.bounded_message) > 512
        ):
            raise ValueError("invalid bounded parser message")
        try:
            self.bounded_message.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise ValueError("parser message must contain Unicode scalar values") from None
        if type(self.detail_sha256) is not str or not _SHA256_PATTERN.fullmatch(
            self.detail_sha256
        ):
            raise ValueError("invalid parser evidence detail SHA-256")


class JsonParseError(ValueError):
    """A local grammar or numeric-domain rejection with bounded evidence."""

    def __init__(self, evidence: JsonParseEvidence) -> None:
        if type(evidence) is not JsonParseEvidence:
            raise TypeError("JSON parse errors require exact parser evidence")
        self.evidence = evidence
        super().__init__(evidence.bounded_message)


@dataclass(slots=True)
class _ArrayFrame:
    depth: int
    items: list[JsonValue] = field(default_factory=list)
    state: str = "first_or_end"


@dataclass(slots=True)
class _ObjectFrame:
    depth: int
    members: list[tuple[JsonString, JsonValue]] = field(default_factory=list)
    names: set[str] = field(default_factory=set)
    pending_key: JsonString | None = None
    state: str = "first_key_or_end"


_Frame = _ArrayFrame | _ObjectFrame


def _hex_value(byte: int) -> int:
    if 0x30 <= byte <= 0x39:
        return byte - 0x30
    if 0x41 <= byte <= 0x46:
        return byte - 0x41 + 10
    if 0x61 <= byte <= 0x66:
        return byte - 0x61 + 10
    return -1


def _utf8_size(code_point: int) -> int:
    if code_point <= 0x7F:
        return 1
    if code_point <= 0x7FF:
        return 2
    if code_point <= 0xFFFF:
        return 3
    return 4


class _Parser:
    __slots__ = ("_artifact_role", "_ledger", "_raw")

    def __init__(self, raw: bytes, artifact_role: str, ledger: BudgetLedger) -> None:
        self._raw = raw
        self._artifact_role = artifact_role
        self._ledger = ledger

    def _reject(self, category: str, index: int) -> None:
        detail = f"{category}\0byte_offset={index}".encode("ascii")
        raise JsonParseError(
            JsonParseEvidence(
                artifact_role=self._artifact_role,
                category=category,
                subject_path=None,
                bounded_message=_CATEGORY_MESSAGES[category],
                detail_sha256=sha256_prefixed(detail),
            )
        )

    def _charge(
        self,
        dimension: BudgetDimension,
        amount: int,
    ) -> None:
        artifact_role = (
            ArtifactRole.COMBINED
            if dimension in _AGGREGATE_DIMENSIONS
            else self._artifact_role
        )
        self._ledger.charge(
            dimension,
            amount,
            artifact_role=artifact_role,
            subject_path=None,
        )

    def _charge_token(self) -> None:
        self._charge(BudgetDimension.PARSER_WORK_UNITS, 1)

    def _charge_node(self) -> None:
        self._charge(BudgetDimension.PARSER_WORK_UNITS, 1)
        self._charge(BudgetDimension.PARSED_NODES, 1)

    def _skip_whitespace(self, index: int) -> int:
        raw = self._raw
        while index < len(raw) and raw[index] in _WHITESPACE:
            index += 1
        return index

    def _validate_utf8(self) -> None:
        index = 0
        while index < len(self._raw):
            if self._raw[index] <= 0x7F:
                index += 1
            else:
                _, index = self._read_utf8(index)

    def _consume_structural(self, index: int, expected: int) -> int:
        if index >= len(self._raw) or self._raw[index] != expected:
            if index < len(self._raw):
                self._charge_token()
            self._reject("invalid_syntax", index)
        self._charge_token()
        return index + 1

    def _read_utf8(self, index: int) -> tuple[int, int]:
        raw = self._raw
        length = len(raw)
        first = raw[index]
        if first <= 0x7F:
            return first, index + 1

        if 0xC2 <= first <= 0xDF:
            needed = 1
            code_point = first & 0x1F
            first_continuation_min = 0x80
            first_continuation_max = 0xBF
        elif 0xE0 <= first <= 0xEF:
            needed = 2
            code_point = first & 0x0F
            first_continuation_min = 0xA0 if first == 0xE0 else 0x80
            first_continuation_max = 0x9F if first == 0xED else 0xBF
        elif 0xF0 <= first <= 0xF4:
            needed = 3
            code_point = first & 0x07
            first_continuation_min = 0x90 if first == 0xF0 else 0x80
            first_continuation_max = 0x8F if first == 0xF4 else 0xBF
        else:
            self._reject("invalid_utf8", index)

        if index + needed >= length:
            self._reject("invalid_utf8", index)
        first_continuation = raw[index + 1]
        if not first_continuation_min <= first_continuation <= first_continuation_max:
            self._reject("invalid_utf8", index)
        code_point = (code_point << 6) | (first_continuation & 0x3F)
        for offset in range(2, needed + 1):
            continuation = raw[index + offset]
            if not 0x80 <= continuation <= 0xBF:
                self._reject("invalid_utf8", index)
            code_point = (code_point << 6) | (continuation & 0x3F)
        return code_point, index + needed + 1

    def _read_hex_quad(self, index: int) -> int:
        if index + 4 > len(self._raw):
            self._reject("invalid_escape", index)
        value = 0
        for offset in range(4):
            digit = _hex_value(self._raw[index + offset])
            if digit < 0:
                self._reject("invalid_escape", index + offset)
            value = (value << 4) | digit
        return value

    def _read_escape(self, escape_index: int) -> tuple[int, int]:
        if escape_index >= len(self._raw):
            self._reject("invalid_escape", escape_index)
        escape = self._raw[escape_index]
        simple = _SIMPLE_ESCAPES.get(escape)
        if simple is not None:
            return simple, escape_index + 1
        if escape != 0x75:
            self._reject("invalid_escape", escape_index)

        code_unit = self._read_hex_quad(escape_index + 1)
        next_index = escape_index + 5
        if 0xDC00 <= code_unit <= 0xDFFF:
            self._reject("invalid_surrogate", escape_index)
        if not 0xD800 <= code_unit <= 0xDBFF:
            return code_unit, next_index

        if (
            next_index + 6 > len(self._raw)
            or self._raw[next_index] != 0x5C
            or self._raw[next_index + 1] != 0x75
        ):
            self._reject("invalid_surrogate", escape_index)
        low = self._read_hex_quad(next_index + 2)
        if not 0xDC00 <= low <= 0xDFFF:
            self._reject("invalid_surrogate", next_index + 1)
        code_point = 0x10000 + ((code_unit - 0xD800) << 10) + low - 0xDC00
        return code_point, next_index + 6

    def _scan_string(self, quote_index: int) -> tuple[int, int]:
        raw = self._raw
        index = quote_index + 1
        decoded_bytes = 0
        while index < len(raw):
            byte = raw[index]
            if byte == 0x22:
                return index + 1, decoded_bytes
            if byte == 0x5C:
                code_point, index = self._read_escape(index + 1)
                decoded_bytes += _utf8_size(code_point)
                continue
            if byte < 0x20:
                self._reject("invalid_syntax", index)
            code_point, index = self._read_utf8(index)
            decoded_bytes += _utf8_size(code_point)
        self._reject("invalid_syntax", len(raw))

    def _decode_string(self, quote_index: int, end_index: int) -> str:
        raw = self._raw
        index = quote_index + 1
        output: list[str] = []
        payload_end = end_index - 1
        while index < payload_end:
            if raw[index] == 0x5C:
                code_point, index = self._read_escape(index + 1)
            else:
                code_point, index = self._read_utf8(index)
            output.append(chr(code_point))
        return "".join(output)

    def _parse_string(
        self,
        quote_index: int,
        *,
        node: bool,
        object_member_count: int | None = None,
    ) -> tuple[int, JsonString]:
        end_index, decoded_bytes = self._scan_string(quote_index)
        self._charge(BudgetDimension.DECODED_STRING_BYTES, decoded_bytes)
        if object_member_count is not None:
            self._charge(BudgetDimension.OBJECT_MEMBERS, object_member_count)
        if node:
            self._charge_node()
        decoded = self._decode_string(quote_index, end_index)
        return end_index, JsonString(decoded)

    def _record_number_character(self, start: int, end: int) -> None:
        self._charge(BudgetDimension.NUMBER_TOKEN_CHARS, end - start)

    def _parse_number(self, start: int) -> tuple[int, JsonNumber]:
        raw = self._raw
        length = len(raw)
        index = start

        if raw[index] == 0x2D:
            index += 1
            self._record_number_character(start, index)
            if index == length:
                self._reject("invalid_number", index)

        if raw[index] == 0x30:
            index += 1
            self._record_number_character(start, index)
            if index < length and 0x30 <= raw[index] <= 0x39:
                self._record_number_character(start, index + 1)
                self._reject("invalid_number", index)
        elif 0x31 <= raw[index] <= 0x39:
            while index < length and 0x30 <= raw[index] <= 0x39:
                index += 1
                self._record_number_character(start, index)
        else:
            self._reject("invalid_number", index)

        classification = "integer"
        if index < length and raw[index] == 0x2E:
            classification = "fraction"
            index += 1
            self._record_number_character(start, index)
            if index == length or not 0x30 <= raw[index] <= 0x39:
                self._reject("invalid_number", index)
            while index < length and 0x30 <= raw[index] <= 0x39:
                index += 1
                self._record_number_character(start, index)

        if index < length and raw[index] in (0x65, 0x45):
            classification = "exponent"
            index += 1
            self._record_number_character(start, index)
            if index < length and raw[index] in (0x2B, 0x2D):
                index += 1
                self._record_number_character(start, index)
            if index == length or not 0x30 <= raw[index] <= 0x39:
                self._reject("invalid_number", index)
            while index < length and 0x30 <= raw[index] <= 0x39:
                index += 1
                self._record_number_character(start, index)

        if index < length and raw[index] not in _TOKEN_BOUNDARIES:
            self._reject("invalid_number", index)

        token = raw[start:index].decode("ascii")
        try:
            value = float(token)
        except (OverflowError, ValueError):
            self._reject("invalid_number", start)
        if not math.isfinite(value):
            self._reject("nonfinite_number", start)
        self._charge_node()
        return index, JsonNumber(value, classification)

    def _parse_literal(
        self,
        index: int,
        literal: bytes,
    ) -> tuple[int, JsonValue]:
        end_index = index + len(literal)
        if self._raw[index:end_index] != literal:
            self._reject("invalid_syntax", index)
        if end_index < len(self._raw) and self._raw[end_index] not in _TOKEN_BOUNDARIES:
            self._reject("invalid_syntax", end_index)
        self._charge_node()
        if literal == b"null":
            value: JsonValue = JsonNull()
        elif literal == b"true":
            value = JsonBoolean(True)
        elif literal == b"false":
            value = JsonBoolean(False)
        else:
            raise AssertionError("unknown fixed JSON literal")
        return end_index, value

    def _start_value(
        self,
        index: int,
        depth: int,
    ) -> tuple[int, JsonValue | None, _Frame | None]:
        self._charge_token()
        byte = self._raw[index]
        if byte == 0x7B:
            self._charge(BudgetDimension.CONTAINER_DEPTH, depth)
            self._charge_node()
            return index + 1, None, _ObjectFrame(depth=depth)
        if byte == 0x5B:
            self._charge(BudgetDimension.CONTAINER_DEPTH, depth)
            self._charge_node()
            return index + 1, None, _ArrayFrame(depth=depth)
        if byte == 0x22:
            end_index, value = self._parse_string(index, node=True)
            return end_index, value, None
        if byte == 0x6E:
            end_index, value = self._parse_literal(index, b"null")
            return end_index, value, None
        if byte == 0x74:
            end_index, value = self._parse_literal(index, b"true")
            return end_index, value, None
        if byte == 0x66:
            end_index, value = self._parse_literal(index, b"false")
            return end_index, value, None
        if byte == 0x2D or 0x30 <= byte <= 0x39:
            end_index, value = self._parse_number(index)
            return end_index, value, None
        self._reject("invalid_syntax", index)

    def _attach(self, frame: _Frame, value: JsonValue) -> None:
        if type(frame) is _ArrayFrame:
            if frame.state != "await_value":
                raise AssertionError("invalid array attachment state")
            frame.items.append(value)
            frame.state = "comma_or_end"
            return
        if frame.state != "await_value" or frame.pending_key is None:
            raise AssertionError("invalid object attachment state")
        frame.members.append((frame.pending_key, value))
        frame.pending_key = None
        frame.state = "comma_or_end"

    def _close_frame(self, frame: _Frame) -> JsonValue:
        if type(frame) is _ArrayFrame:
            return JsonArray(tuple(frame.items))
        return _seal_object_members(tuple(frame.members))

    def _begin_array_item(
        self,
        frame: _ArrayFrame,
        index: int,
    ) -> tuple[int, JsonValue | None, _Frame | None]:
        item_count = len(frame.items) + 1
        self._charge(BudgetDimension.ARRAY_ITEMS, item_count)
        self._charge(BudgetDimension.PARSER_WORK_UNITS, 1)
        frame.state = "await_value"
        return self._start_value(index, frame.depth + 1)

    def _read_object_key(self, frame: _ObjectFrame, index: int) -> int:
        self._charge_token()
        if self._raw[index] != 0x22:
            self._reject("invalid_syntax", index)
        member_count = len(frame.members) + 1
        end_index, key = self._parse_string(
            index,
            node=False,
            object_member_count=member_count,
        )
        if key.value in frame.names:
            self._reject("duplicate_member", index)
        frame.names.add(key.value)
        frame.pending_key = key
        frame.state = "colon"
        return end_index

    def parse(self) -> JsonValue:
        raw = self._raw
        raw_block_units = (len(self._raw) + 63) // 64
        self._charge(BudgetDimension.PARSER_WORK_UNITS, raw_block_units)
        if self._raw.startswith(b"\xef\xbb\xbf"):
            self._reject("bom_not_allowed", 0)
        self._validate_utf8()

        index = 0
        root: JsonValue | None = None
        root_complete = False
        pending_value: JsonValue | None = None
        frames: list[_Frame] = []

        while True:
            if pending_value is not None:
                if frames:
                    self._attach(frames[-1], pending_value)
                else:
                    root = pending_value
                    root_complete = True
                pending_value = None
                continue

            if not frames:
                if root_complete:
                    index = self._skip_whitespace(index)
                    if index != len(self._raw):
                        self._charge_token()
                        self._reject("invalid_syntax", index)
                    if root is None:
                        raise AssertionError("completed JSON root is missing")
                    return root

                index = self._skip_whitespace(index)
                if index == len(self._raw):
                    self._reject("invalid_syntax", index)
                index, pending_value, new_frame = self._start_value(index, 1)
                if new_frame is not None:
                    frames.append(new_frame)
                continue

            frame = frames[-1]
            index = self._skip_whitespace(index)
            if type(frame) is _ArrayFrame:
                if frame.state == "first_or_end":
                    if index < len(raw) and raw[index] == 0x5D:
                        index = self._consume_structural(index, 0x5D)
                        frames.pop()
                        pending_value = self._close_frame(frame)
                        continue
                    if index == len(raw):
                        self._reject("invalid_syntax", index)
                    index, pending_value, new_frame = self._begin_array_item(frame, index)
                    if new_frame is not None:
                        frames.append(new_frame)
                    continue
                if frame.state == "value":
                    if index == len(raw):
                        self._reject("invalid_syntax", index)
                    if raw[index] == 0x5D:
                        self._charge_token()
                        self._reject("invalid_syntax", index)
                    index, pending_value, new_frame = self._begin_array_item(frame, index)
                    if new_frame is not None:
                        frames.append(new_frame)
                    continue
                if frame.state == "comma_or_end":
                    if index == len(raw):
                        self._reject("invalid_syntax", index)
                    if raw[index] == 0x2C:
                        index = self._consume_structural(index, 0x2C)
                        frame.state = "value"
                        continue
                    if raw[index] == 0x5D:
                        index = self._consume_structural(index, 0x5D)
                        frames.pop()
                        pending_value = self._close_frame(frame)
                        continue
                    self._charge_token()
                    self._reject("invalid_syntax", index)
                raise AssertionError("invalid array parser state")

            if frame.state in ("first_key_or_end", "key"):
                if index == len(raw):
                    self._reject("invalid_syntax", index)
                if raw[index] == 0x7D:
                    if frame.state == "key":
                        self._charge_token()
                        self._reject("invalid_syntax", index)
                    index = self._consume_structural(index, 0x7D)
                    frames.pop()
                    pending_value = self._close_frame(frame)
                    continue
                index = self._read_object_key(frame, index)
                continue
            if frame.state == "colon":
                index = self._consume_structural(index, 0x3A)
                frame.state = "value"
                continue
            if frame.state == "value":
                if index == len(raw):
                    self._reject("invalid_syntax", index)
                self._charge(BudgetDimension.PARSER_WORK_UNITS, 1)
                frame.state = "await_value"
                index, pending_value, new_frame = self._start_value(index, frame.depth + 1)
                if new_frame is not None:
                    frames.append(new_frame)
                continue
            if frame.state == "comma_or_end":
                if index == len(raw):
                    self._reject("invalid_syntax", index)
                if raw[index] == 0x2C:
                    index = self._consume_structural(index, 0x2C)
                    frame.state = "key"
                    continue
                if raw[index] == 0x7D:
                    index = self._consume_structural(index, 0x7D)
                    frames.pop()
                    pending_value = self._close_frame(frame)
                    continue
                self._charge_token()
                self._reject("invalid_syntax", index)
            raise AssertionError("invalid object parser state")


def parse_owned_json(
    raw: bytes,
    *,
    artifact_role: str,
    ledger: BudgetLedger,
) -> ParsedJsonValue:
    """Parse admitted exact bytes directly into one immutable owned value."""

    if type(raw) is not bytes:
        raise TypeError("JSON parser requires exact built-in bytes")
    if type(artifact_role) is not str:
        raise TypeError("JSON parser artifact role must be an exact str")
    if artifact_role not in _PARSE_ARTIFACT_ROLES:
        raise ValueError("JSON parser artifact role is not parseable")
    if type(ledger) is not BudgetLedger:
        raise TypeError("JSON parser requires an exact invocation budget ledger")

    value = _Parser(raw, artifact_role, ledger).parse()
    return ParsedJsonValue(
        value=value,
        value_fingerprint=canonical_fingerprint_metered(
            value,
            lambda blocks: ledger.charge(
                BudgetDimension.PARSER_WORK_UNITS,
                blocks,
                artifact_role=ArtifactRole.COMBINED,
                subject_path=None,
            ),
        ),
    )


__all__ = (
    "JsonParseError",
    "JsonParseEvidence",
    "ParsedJsonValue",
    "parse_owned_json",
)
