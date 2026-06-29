import pytest


DEFAULT_OUTPUT_DIRECTORY = "C:/tmp/rook-mesh2splat"


def valid_request(**overrides):
    payload = {
        "outputDirectory": DEFAULT_OUTPUT_DIRECTORY,
    }
    payload.update(overrides)
    return payload


def assert_validation_envelope(payload, expected):
    from rook.mesh2splat.contracts import RequestValidationError, validate_request

    with pytest.raises(RequestValidationError) as exc:
        validate_request(payload, default_sampling_resolution=128)

    assert exc.value.envelope == expected


def test_output_directory_is_required_and_absolute():
    assert_validation_envelope(
        {},
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "outputDirectory is required and must be an absolute path",
                "retryable": False,
            },
        },
    )
    assert_validation_envelope(
        {"outputDirectory": "relative/out"},
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "outputDirectory is required and must be an absolute path",
                "retryable": False,
            },
        },
    )


@pytest.mark.parametrize("format_name", ["compressed-pbr", "standard"])
def test_format_accepts_supported_values(format_name):
    from rook.mesh2splat.contracts import validate_request

    request = validate_request(
        valid_request(format=format_name, allowLargeOutput=True),
        default_sampling_resolution=128,
    )

    assert request.format == format_name


def test_format_rejects_unsupported_values():
    assert_validation_envelope(
        valid_request(format="ply"),
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "format must be one of: compressed-pbr, standard",
                "retryable": False,
            },
        },
    )


@pytest.mark.parametrize("resolution", [16, 128, 4096])
def test_sampling_resolution_accepts_integer_range(resolution):
    from rook.mesh2splat.contracts import validate_request

    request = validate_request(
        valid_request(samplingResolution=resolution, allowLargeOutput=True),
        default_sampling_resolution=128,
    )

    assert request.sampling_resolution == resolution


@pytest.mark.parametrize("resolution", [15, 4097, 128.0, "128", True])
def test_sampling_resolution_rejects_non_integer_or_out_of_range_values(resolution):
    assert_validation_envelope(
        valid_request(samplingResolution=resolution),
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "samplingResolution must be an integer from 16 to 4096",
                "retryable": False,
            },
        },
    )


def test_sampling_resolution_defaults_from_argument():
    from rook.mesh2splat.contracts import validate_request

    request = validate_request(valid_request(), default_sampling_resolution=128)

    assert request.sampling_resolution == 128


@pytest.mark.parametrize(
    "payload",
    [
        valid_request(samplingResolution=513),
        valid_request(format="standard"),
    ],
)
def test_large_output_requires_explicit_opt_in(payload):
    assert_validation_envelope(
        payload,
        {
            "success": False,
            "data": {
                "code": "large_output_requires_opt_in",
                "message": "samplingResolution > 512 or format standard requires allowLargeOutput=true",
                "retryable": False,
            },
        },
    )


@pytest.mark.parametrize("units_mode", ["meters", "raw"])
def test_units_mode_accepts_supported_values(units_mode):
    from rook.mesh2splat.contracts import validate_request

    request = validate_request(
        valid_request(unitsMode=units_mode),
        default_sampling_resolution=128,
    )

    assert request.units_mode == units_mode


def test_units_mode_defaults_to_meters():
    from rook.mesh2splat.contracts import DEFAULT_UNITS_MODE, validate_request

    request = validate_request(valid_request(), default_sampling_resolution=128)

    assert request.units_mode == "meters"
    assert DEFAULT_UNITS_MODE == "meters"


def test_units_mode_rejects_unsupported_values():
    assert_validation_envelope(
        valid_request(unitsMode="millimeters"),
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "unitsMode must be one of: meters, raw",
                "retryable": False,
            },
        },
    )


def test_first_slice_request_options_are_parsed():
    from rook.mesh2splat.contracts import Mesh2SplatRequest, validate_request

    request = validate_request(
        {
            "outputDirectory": DEFAULT_OUTPUT_DIRECTORY,
            "format": "compressed-pbr",
            "samplingResolution": 256,
            "unitsMode": "raw",
            "allowLargeOutput": False,
            "allowNetworkTextures": True,
            "preserveDebugArtifacts": True,
            "object_ids": ["a", "b"],
            "allowPartial": True,
            "mesh2splatPath": "C:/tools/mesh2splat.exe",
            "mesh2splatWorkingDirectory": "C:/tmp/mesh2splat-work",
            "mesh2splatTimeoutSeconds": 90,
        },
        default_sampling_resolution=128,
    )

    assert isinstance(request, Mesh2SplatRequest)
    assert request.output_directory == DEFAULT_OUTPUT_DIRECTORY
    assert request.format == "compressed-pbr"
    assert request.sampling_resolution == 256
    assert request.units_mode == "raw"
    assert request.allow_large_output is False
    assert request.allow_network_textures is True
    assert request.preserve_debug_artifacts is True
    assert request.object_ids == ("a", "b")
    assert request.allow_partial is True
    assert request.mesh2splat_path == "C:/tools/mesh2splat.exe"
    assert request.mesh2splat_working_directory == "C:/tmp/mesh2splat-work"
    assert request.mesh2splat_timeout_seconds == 90


@pytest.mark.parametrize("timeout_seconds", [0, -1])
def test_mesh2splat_timeout_seconds_rejects_non_positive_values(timeout_seconds):
    assert_validation_envelope(
        valid_request(mesh2splatTimeoutSeconds=timeout_seconds),
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "mesh2splatTimeoutSeconds must be a positive integer",
                "retryable": False,
            },
        },
    )


def test_object_ids_rejects_explicit_empty_list():
    assert_validation_envelope(
        valid_request(object_ids=[]),
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "object_ids must be a non-empty list of strings",
                "retryable": False,
            },
        },
    )


def test_object_ids_rejects_explicit_null():
    assert_validation_envelope(
        valid_request(object_ids=None),
        {
            "success": False,
            "data": {
                "code": "invalid_request",
                "message": "object_ids must be a non-empty list of strings",
                "retryable": False,
            },
        },
    )


def test_object_ids_omission_uses_current_selection():
    from rook.mesh2splat.contracts import validate_request

    request = validate_request(valid_request(), default_sampling_resolution=128)

    assert request.object_ids is None


def test_object_ids_are_stored_immutably_without_aliasing_caller_list():
    from rook.mesh2splat.contracts import validate_request

    caller_object_ids = ["a", "b"]
    request = validate_request(
        valid_request(object_ids=caller_object_ids),
        default_sampling_resolution=128,
    )

    caller_object_ids.append("c")

    assert request.object_ids == ("a", "b")


def test_required_constants_are_exposed():
    from rook.mesh2splat import contracts

    assert contracts.DEFAULT_FORMAT == "compressed-pbr"
    assert contracts.DEFAULT_UNITS_MODE == "meters"
    assert contracts.VALID_FORMATS == {"compressed-pbr", "standard"}
    assert contracts.MIN_SAMPLING_RESOLUTION == 16
    assert contracts.MAX_SAMPLING_RESOLUTION == 4096
    assert contracts.LARGE_OUTPUT_SAMPLING_THRESHOLD == 512
    assert contracts.MESH2SPLAT_MAX_GAUSSIANS == 7_000_000
    assert contracts.FORMAT_STRIDES == {"compressed-pbr": 48, "standard": 248}
