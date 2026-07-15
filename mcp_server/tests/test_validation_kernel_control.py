from __future__ import annotations

import hashlib

import pytest

from rook.validation_kernel.control import (
    ArtifactRole,
    FailureStage,
    ValidationControlFailure,
    control_failure_from_exception,
)


_OPAQUE_EXCEPTION_MARKER = b"rook.validation_kernel.caught_exception:v1"


class _HostileExceptionMeta(type):
    def __getattribute__(cls, name: str) -> object:
        if name in ("__module__", "__qualname__") and type.__getattribute__(
            cls, "_metadata_is_hostile"
        ):
            raise RuntimeError("exception type metadata escaped")
        return type.__getattribute__(cls, name)


class _HostileException(Exception, metaclass=_HostileExceptionMeta):
    _metadata_is_hostile = False


@pytest.mark.parametrize("raw_input", (None, b'{"hostile":true}'))
def test_exception_projection_uses_fixed_opaque_marker_without_type_metadata(
    raw_input: bytes | None,
) -> None:
    exception = _HostileException("attacker-controlled text")
    type.__setattr__(_HostileException, "_metadata_is_hostile", True)
    try:
        result = control_failure_from_exception(
            failure_stage=FailureStage.VALIDATION,
            code="validator_internal_failure",
            artifact_role=ArtifactRole.REPORT_SEAL,
            program_id="synthetic.validation_program:v1",
            program_fingerprint="sha256:" + ("1" * 64),
            subject_path=None,
            exception=exception,
            raw_input=raw_input,
        )
    finally:
        type.__setattr__(_HostileException, "_metadata_is_hostile", False)

    detail = (
        _OPAQUE_EXCEPTION_MARKER
        if raw_input is None
        else _OPAQUE_EXCEPTION_MARKER + b"\0" + raw_input
    )
    assert type(result) is ValidationControlFailure
    assert result.code == "validator_internal_failure"
    assert result.detail_sha256 == f"sha256:{hashlib.sha256(detail).hexdigest()}"
