"""Fixed bootstrap schemas owned by the validation kernel seal."""

from __future__ import annotations

import json

from .canonical_json import canonical_fingerprint
from .owned_json import JsonObject, own_trusted_json


PROGRAM_MANIFEST_SCHEMA_ID = "rook.validation_program_manifest:v1"
TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID = (
    "rook.trusted_bundle_assembler_profile:v1"
)
CONFORMANCE_GATE_PROFILE_SCHEMA_ID = "rook.validation_conformance_gate_profile:v1"
CONFORMANCE_CAMPAIGN_SCHEMA_ID = "rook.validation_conformance_campaign:v1"
CONFORMANCE_FIXTURE_SCHEMA_ID = "rook.validation_conformance_fixture:v1"
CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_ID = (
    "rook.validation_conformance_schema_attempt:v1"
)
CONFORMANCE_COMPLETENESS_SCHEMA_ID = (
    "rook.validation_conformance_completeness:v1"
)
CONFORMANCE_REPORT_SCHEMA_ID = "rook.validation_conformance_report:v1"
BUDGET_RECEIPT_NESTED_FIELD_COUNT = 19
KERNEL_REPORT_FIELD_ROLES = (
    ("budget_receipt", "/validation_budget", "object"),
    ("report_fingerprint", "/report_fingerprint", "string"),
)
REPORT_BUDGET_RECEIPT_PATH = KERNEL_REPORT_FIELD_ROLES[0][1]
REPORT_FINGERPRINT_PATH = KERNEL_REPORT_FIELD_ROLES[1][1]
KERNEL_OWNED_REPORT_PATHS = tuple(
    sorted(role[1] for role in KERNEL_REPORT_FIELD_ROLES)
)
FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT = (
    BUDGET_RECEIPT_NESTED_FIELD_COUNT + len(KERNEL_OWNED_REPORT_PATHS)
)

_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_MACHINE_ID = {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"}
_FINGERPRINT = {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"}
_CARDINALITY = {"enum": ["exactly_one", "zero_or_one", "many"]}
_STATUS = {"enum": ["passed", "blocked", "failed"]}


def _closed_object(properties: dict[str, object], required: tuple[str, ...] | None = None) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required or tuple(properties)),
        "additionalProperties": False,
    }


_RUNTIME_COMPONENT = _closed_object(
    {
        "component_id": {"$ref": "#/$defs/machine_id"},
        "implementation_id": {"$ref": "#/$defs/machine_id"},
        "implementation_fingerprint": {"$ref": "#/$defs/fingerprint"},
        "source_module": {"$ref": "#/$defs/module_name"},
        "callable_record_state_canonical_json": {
            "type": ["string", "null"]
        },
        "callable_record_state_fingerprint": {
            "anyOf": [
                {"$ref": "#/$defs/fingerprint"},
                {"type": "null"},
            ]
        },
    }
)

_INPUT_BINDING = _closed_object(
    {
        "input_name": {"$ref": "#/$defs/machine_id"},
        "source_kind": {
            "enum": ["invocation_input", "program_constant", "phase_output"]
        },
        "source_input": {
            "anyOf": [{"$ref": "#/$defs/machine_id"}, {"type": "null"}]
        },
        "source_constant": {
            "anyOf": [{"$ref": "#/$defs/machine_id"}, {"type": "null"}]
        },
        "source_phase": {
            "anyOf": [{"$ref": "#/$defs/machine_id"}, {"type": "null"}]
        },
        "source_output": {
            "anyOf": [{"$ref": "#/$defs/machine_id"}, {"type": "null"}]
        },
        "expected_type": {"$ref": "#/$defs/machine_id"},
        "cardinality": {"$ref": "#/$defs/cardinality"},
        "binding_fingerprint": {"$ref": "#/$defs/fingerprint"},
    }
)

_PROVIDED_OUTPUT = _closed_object(
    {
        "output_name": {"$ref": "#/$defs/machine_id"},
        "output_type": {"$ref": "#/$defs/machine_id"},
        "cardinality": {"$ref": "#/$defs/cardinality"},
        "permitted_on_statuses": {
            "type": "array",
            "items": {"$ref": "#/$defs/status"},
            "uniqueItems": True,
            "minItems": 1,
        },
        "required_on_statuses": {
            "type": "array",
            "items": {"$ref": "#/$defs/status"},
            "uniqueItems": True,
        },
        "output_fingerprint": {"$ref": "#/$defs/fingerprint"},
    }
)

_PHASE = _closed_object(
    {
        "phase_name": {"$ref": "#/$defs/machine_id"},
        "ordering_after": {
            "type": "array",
            "items": {"$ref": "#/$defs/machine_id"},
            "uniqueItems": True,
        },
        "input_bindings": {
            "type": "array",
            "items": {"$ref": "#/$defs/input_binding"},
        },
        "provided_outputs": {
            "type": "array",
            "items": {"$ref": "#/$defs/provided_output"},
        },
        "runner_id": {"$ref": "#/$defs/machine_id"},
        "permitted_diagnostic_codes": {
            "type": "array",
            "items": {"$ref": "#/$defs/machine_id"},
            "uniqueItems": True,
        },
        "permitted_blocker_codes": {
            "type": "array",
            "items": {"$ref": "#/$defs/machine_id"},
            "uniqueItems": True,
        },
        "phase_fingerprint": {"$ref": "#/$defs/fingerprint"},
    }
)

_BUDGET_LIMIT_NAMES = (
    "recipe_input_bytes",
    "validation_bundle_input_bytes",
    "container_depth",
    "number_token_chars",
    "parsed_nodes",
    "object_members",
    "array_items",
    "decoded_string_bytes",
    "parser_work_units",
    "semantic_references",
    "schema_evaluation_shape_units",
    "diagnostics",
    "compile_blockers",
    "kernel_phase_work_units",
    "report_canonical_bytes",
    "report_projection_fields",
    "report_seal_work_units",
)
_BUDGET_LIMITS = _closed_object(
    {name: {"type": "integer", "minimum": 0} for name in _BUDGET_LIMIT_NAMES}
)

_PROGRAM_MANIFEST_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": PROGRAM_MANIFEST_SCHEMA_ID,
    "$defs": {
        "machine_id": _MACHINE_ID,
        "module_name": {
            "type": "string",
            "pattern": r"^[A-Za-z_][A-Za-z0-9_.]{0,255}$",
        },
        "fingerprint": _FINGERPRINT,
        "cardinality": _CARDINALITY,
        "status": _STATUS,
        "runtime_component": _RUNTIME_COMPONENT,
        "input_binding": _INPUT_BINDING,
        "provided_output": _PROVIDED_OUTPUT,
        "phase": _PHASE,
        "budget_limits": _BUDGET_LIMITS,
    },
    **_closed_object(
        {
            "schema": {"const": PROGRAM_MANIFEST_SCHEMA_ID},
            "program_id": {"$ref": "#/$defs/machine_id"},
            "kernel_abi_version": {"const": "rook.validation_kernel:v1"},
            "kernel_build_fingerprint": {"$ref": "#/$defs/fingerprint"},
            "program_seal_profile": {"const": "rook.validation_program_seal:v1"},
            "program_seal_implementation_fingerprint": {
                "$ref": "#/$defs/fingerprint"
            },
            "bootstrap_seal": _closed_object(
                {
                    "manifest_schema_id": {
                        "const": PROGRAM_MANIFEST_SCHEMA_ID
                    },
                    "manifest_schema_fingerprint": {
                        "$ref": "#/$defs/fingerprint"
                    },
                    "canonicalization_version": {
                        "const": "rook.canonical_json:v1"
                    },
                    "reference_canonicalizer_id": {
                        "$ref": "#/$defs/machine_id"
                    },
                    "reference_canonicalizer_fingerprint": {
                        "$ref": "#/$defs/fingerprint"
                    },
                    "hash_algorithm": {"const": "sha256"},
                    "hash_implementation_id": {
                        "const": "python.hashlib.sha256:v1"
                    },
                }
            ),
            "budget_manifest": _closed_object(
                {
                    "profile_id": {"$ref": "#/$defs/machine_id"},
                    "limits": {"$ref": "#/$defs/budget_limits"},
                    "limits_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    "budget_fingerprint": {"$ref": "#/$defs/fingerprint"},
                }
            ),
            "parser_profile": _closed_object(
                {
                    "profile_id": {"$ref": "#/$defs/machine_id"},
                    "tokenizer": {"$ref": "#/$defs/runtime_component"},
                    "parser": {"$ref": "#/$defs/runtime_component"},
                    "canonicalizer": {"$ref": "#/$defs/runtime_component"},
                    "ledger": {"$ref": "#/$defs/runtime_component"},
                    "tokenizer_version": {"$ref": "#/$defs/machine_id"},
                    "parser_version": {"$ref": "#/$defs/machine_id"},
                    "owned_value_abi": {"$ref": "#/$defs/machine_id"},
                    "canonicalization_version": {
                        "$ref": "#/$defs/machine_id"
                    },
                    "profile_fingerprint": {"$ref": "#/$defs/fingerprint"},
                }
            ),
            "schema_evaluator_profiles": {
                "type": "array",
                "items": _closed_object(
                    {
                        "profile_id": {"$ref": "#/$defs/machine_id"},
                        "allowed_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "uniqueItems": True,
                        },
                        "forbidden_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "uniqueItems": True,
                        },
                        "limits": _closed_object(
                            {
                                "schema_nodes": {"type": "integer", "minimum": 0},
                                "local_references": {"type": "integer", "minimum": 0},
                                "local_reference_depth": {"type": "integer", "minimum": 0},
                                "per_evaluation_shape_units": {"type": "integer", "minimum": 0},
                                "combinator_alternatives": {"type": "integer", "minimum": 0},
                                "combinator_depth": {"type": "integer", "minimum": 0},
                            }
                        ),
                        "runtime_dependencies": {
                            "type": "array",
                            "items": _closed_object(
                                {
                                    "distribution": {"type": "string"},
                                    "version": {"type": "string"},
                                }
                            ),
                        },
                        "metaschema_id": {"type": "string"},
                        "metaschema_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "evaluator_id": {"$ref": "#/$defs/machine_id"},
                        "type_checker_id": {"$ref": "#/$defs/machine_id"},
                        "format_policy_id": {"$ref": "#/$defs/machine_id"},
                        "reference_policy_id": {"$ref": "#/$defs/machine_id"},
                        "identity_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "evaluator": {"$ref": "#/$defs/runtime_component"},
                    }
                ),
            },
            "schemas": {
                "type": "array",
                "items": _closed_object(
                    {
                        "schema_id": {"$ref": "#/$defs/machine_id"},
                        "schema_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "profile_id": {"$ref": "#/$defs/machine_id"},
                        "schema_nodes": {"type": "integer", "minimum": 1},
                        "local_reference_count": {"type": "integer", "minimum": 0},
                        "maximum_reference_depth": {"type": "integer", "minimum": 0},
                    }
                ),
            },
            "invocation_inputs": {
                "type": "array",
                "items": _closed_object(
                    {
                        "input_name": {"$ref": "#/$defs/machine_id"},
                        "value_type": {"$ref": "#/$defs/machine_id"},
                        "cardinality": {"$ref": "#/$defs/cardinality"},
                        "input_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    }
                ),
            },
            "program_constants": {
                "type": "array",
                "items": _closed_object(
                    {
                        "constant_name": {"$ref": "#/$defs/machine_id"},
                        "value_type": {"$ref": "#/$defs/machine_id"},
                        "cardinality": {"$ref": "#/$defs/cardinality"},
                        "value_fingerprint": {"$ref": "#/$defs/fingerprint"},
                        "constant_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    }
                ),
            },
            "phases": {
                "type": "array",
                "items": {"$ref": "#/$defs/phase"},
            },
            "runners": {
                "type": "array",
                "items": {"$ref": "#/$defs/runtime_component"},
            },
            "issue_vocabulary": {
                "type": "array",
                "items": _closed_object(
                    {
                        "code": {"$ref": "#/$defs/machine_id"},
                        "classification": {
                            "enum": ["diagnostic", "compile_blocker"]
                        },
                        "issue_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    }
                ),
            },
            "export_types": {
                "type": "array",
                "items": _closed_object(
                    {
                        "export_type": {"$ref": "#/$defs/machine_id"},
                        "validator": {"$ref": "#/$defs/runtime_component"},
                        "export_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    }
                ),
            },
            "report_projection": _closed_object(
                {
                    "projection_id": {"$ref": "#/$defs/machine_id"},
                    "implementation_id": {"$ref": "#/$defs/machine_id"},
                    "implementation_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    "source_module": {"$ref": "#/$defs/module_name"},
                    "callable_record_state_canonical_json": {
                        "type": ["string", "null"]
                    },
                    "callable_record_state_fingerprint": {
                        "anyOf": [
                            {"$ref": "#/$defs/fingerprint"},
                            {"type": "null"},
                        ]
                    },
                    "output_schema_id": {"$ref": "#/$defs/machine_id"},
                    "output_schema_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    "report_fingerprint_path": {"type": "string"},
                    "fingerprint_excluded_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "input_envelope_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "required_for_compile_phases": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/machine_id"},
                        "uniqueItems": True,
                    },
                    "kernel_owned_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "budget_receipt_path": {"type": "string"},
                    "writable_body_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "mandatory_shells": {
                        "type": "array",
                        "items": _closed_object(
                            {
                                "path": {"type": "string"},
                                "container_kind": {"enum": ["object", "array"]},
                            }
                        ),
                    },
                    "outer_envelope_field_count": {
                        "type": "integer",
                        "minimum": 1,
                    },
                    "projection_fingerprint": {"$ref": "#/$defs/fingerprint"},
                }
            ),
            "implementation_sources": {
                "type": "array",
                "items": _closed_object(
                    {
                        "module_name": {"$ref": "#/$defs/module_name"},
                        "source_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    }
                ),
            },
            "runtime_dependencies": {
                "type": "array",
                "items": _closed_object(
                    {
                        "distribution_name": {"type": "string"},
                        "version": {"type": "string"},
                        "activated_extras": {
                            "type": "array",
                            "items": {"type": "string"},
                            "uniqueItems": True,
                        },
                        "active_runtime_requirements": {
                            "type": "array",
                            "items": _closed_object(
                                {
                                    "distribution_name": {"type": "string"},
                                    "extras": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "uniqueItems": True,
                                    },
                                    "specifier": {"type": "string"},
                                    "url": {"type": ["string", "null"]},
                                    "marker": {"type": ["string", "null"]},
                                }
                            ),
                        },
                        "file_records": {
                            "type": "array",
                            "items": _closed_object(
                                {
                                    "path": {"type": "string"},
                                    "sha256": {"$ref": "#/$defs/fingerprint"},
                                    "size": {"type": "integer", "minimum": 0},
                                }
                            ),
                        },
                        "behavior_files": {
                            "type": "array",
                            "items": _closed_object(
                                {
                                    "path": {"type": "string"},
                                    "sha256": {"$ref": "#/$defs/fingerprint"},
                                }
                            ),
                        },
                        "distribution_fingerprint": {"$ref": "#/$defs/fingerprint"},
                    }
                ),
            },
            "python_runtime": _closed_object(
                {
                    "implementation": {"type": "string"},
                    "version": {
                        "type": "array",
                        "prefixItems": [
                            {"type": "integer"},
                            {"type": "integer"},
                            {"type": "integer"},
                            {"type": "string"},
                            {"type": "integer"},
                        ],
                        "items": False,
                        "minItems": 5,
                        "maxItems": 5,
                    },
                    "cache_tag": {"type": "string"},
                    "runtime_fingerprint": {"$ref": "#/$defs/fingerprint"},
                }
            ),
            "program_fingerprint": {"$ref": "#/$defs/fingerprint"},
        }
    ),
}

_TRUSTED_ASSEMBLER_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID,
    **_closed_object(
        {
            "schema": {"const": TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID},
            "profile_id": _MACHINE_ID,
            "assembler_kind": {
                "enum": ["trusted_host_ingress", "deterministic_fixture"]
            },
            "assembler_id": _MACHINE_ID,
            "assembler_version": _MACHINE_ID,
            "implementation_fingerprint": _FINGERPRINT,
            "permitted_program_ids": {
                "type": "array",
                "items": _MACHINE_ID,
                "minItems": 1,
                "uniqueItems": True,
            },
            "permitted_clock_sources": {
                "type": "array",
                "items": {
                    "enum": ["trusted_system_clock", "deterministic_fixture"]
                },
                "minItems": 1,
                "uniqueItems": True,
            },
            "profile_fingerprint": _FINGERPRINT,
        }
    ),
}

_NULLABLE_FINGERPRINT = {
    "anyOf": [_FINGERPRINT, {"type": "null"}],
}
_NULLABLE_MACHINE_ID = {
    "anyOf": [_MACHINE_ID, {"type": "null"}],
}

_CONFORMANCE_GATE_PROFILE_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": CONFORMANCE_GATE_PROFILE_SCHEMA_ID,
    **_closed_object(
        {
            "schema": {"const": CONFORMANCE_GATE_PROFILE_SCHEMA_ID},
            "gate_profile_id": _MACHINE_ID,
            "gate_profile_version": _MACHINE_ID,
            "gate_implementation_fingerprint": _FINGERPRINT,
            "budget_profile": _MACHINE_ID,
            "limits_fingerprint": _FINGERPRINT,
            "campaign_input_byte_limit": {"const": 4_194_304},
            "referenced_case_content_byte_limit": {"const": 4_194_304},
            "gate_profile_fingerprint": _FINGERPRINT,
        }
    ),
}

_CORE_CAMPAIGN_CASE = _closed_object(
    {
        "case_id": _MACHINE_ID,
        "case_kind": {"const": "core_schema_positive"},
        "schema_case": _closed_object(
            {
                "schema_id": _MACHINE_ID,
                "schema_fingerprint": _FINGERPRINT,
                "instance_fingerprint": _FINGERPRINT,
                "instance_content_ref": _MACHINE_ID,
            }
        ),
        "fixture_case": {"type": "null"},
        "case_fingerprint": _FINGERPRINT,
    }
)
_FIXTURE_CAMPAIGN_CASE = _closed_object(
    {
        "case_id": _MACHINE_ID,
        "case_kind": {"const": "semantic_fixture"},
        "schema_case": {"type": "null"},
        "fixture_case": _closed_object(
            {
                "fixture_fingerprint": _FINGERPRINT,
                "fixture_content_ref": _MACHINE_ID,
                "recipe_input_payload_sha256": _FINGERPRINT,
                "validation_bundle_input_payload_sha256": _FINGERPRINT,
                "assembler_profile_fingerprint": _FINGERPRINT,
            }
        ),
        "case_fingerprint": _FINGERPRINT,
    }
)
_CONFORMANCE_CAMPAIGN_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": CONFORMANCE_CAMPAIGN_SCHEMA_ID,
    **_closed_object(
        {
            "schema": {"const": CONFORMANCE_CAMPAIGN_SCHEMA_ID},
            "campaign_id": _MACHINE_ID,
            "campaign_version": _MACHINE_ID,
            "program_id": _MACHINE_ID,
            "program_fingerprint": _FINGERPRINT,
            "required_gate_profile_fingerprint": _FINGERPRINT,
            "required_cases": {
                "type": "array",
                "items": {
                    "oneOf": [_CORE_CAMPAIGN_CASE, _FIXTURE_CAMPAIGN_CASE]
                },
                "minItems": 1,
                "maxItems": 16_384,
            },
            "required_case_set_fingerprint": _FINGERPRINT,
            "campaign_fingerprint": _FINGERPRINT,
        }
    ),
}

_PUBLISHED_EXPECTED_RESULT = _closed_object(
    {
        "result_kind": {"const": "published_report"},
        "report_schema_id": _MACHINE_ID,
        "report_fingerprint": _FINGERPRINT,
        "control_failure_stage": {"type": "null"},
        "control_failure_code": {"type": "null"},
        "control_failure_artifact_role": {"type": "null"},
    }
)
_CONTROL_EXPECTED_RESULT = _closed_object(
    {
        "result_kind": {"const": "control_failure"},
        "report_schema_id": {"type": "null"},
        "report_fingerprint": {"type": "null"},
        "control_failure_stage": {"enum": ["preflight", "validation"]},
        "control_failure_code": _MACHINE_ID,
        "control_failure_artifact_role": _MACHINE_ID,
    }
)
_CONFORMANCE_FIXTURE_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": CONFORMANCE_FIXTURE_SCHEMA_ID,
    **_closed_object(
        {
            "schema": {"const": CONFORMANCE_FIXTURE_SCHEMA_ID},
            "fixture_id": _MACHINE_ID,
            "recipe_input": _closed_object(
                {
                    "content_ref": _MACHINE_ID,
                    "input_payload_sha256": _FINGERPRINT,
                }
            ),
            "validation_bundle_input": _closed_object(
                {
                    "content_ref": _MACHINE_ID,
                    "input_payload_sha256": _FINGERPRINT,
                }
            ),
            "assembler_profile_fingerprint": _FINGERPRINT,
            "expected_result": {
                "oneOf": [_PUBLISHED_EXPECTED_RESULT, _CONTROL_EXPECTED_RESULT]
            },
            "fixture_fingerprint": _FINGERPRINT,
        }
    ),
}

_INSTANCE_BINDING = _closed_object(
    {
        "artifact_id": _MACHINE_ID,
        "artifact_fingerprint": _FINGERPRINT,
    }
)
_ATTEMPT_PROPERTIES = {
    "evaluation_index": {"type": "integer", "minimum": 0},
    "schema_id": _MACHINE_ID,
    "schema_fingerprint": _FINGERPRINT,
    "instance_binding": _INSTANCE_BINDING,
    "instance_pointer": {"type": "string"},
    "instance_fingerprint": _FINGERPRINT,
    "attempt_status": {
        "enum": [
            "reservation_rejected",
            "evaluation_completed",
            "evaluator_failed",
        ]
    },
    "schema_nodes": {"type": "integer", "minimum": 0},
    "instance_nodes": {"type": "integer", "minimum": 0},
    "attempted_shape_units": {
        "type": ["integer", "null"],
        "minimum": 0,
    },
    "per_evaluation_limit": {"type": "integer", "minimum": 0},
    "aggregate_before_reservation": {"type": "integer", "minimum": 0},
    "aggregate_after_reservation": {
        "type": ["integer", "null"],
        "minimum": 0,
    },
    "evaluator_invoked": {"type": "boolean"},
    "evaluation_passed": {"type": ["boolean", "null"]},
    "failure_code": {
        "enum": [
            None,
            "per_evaluation_limit_exceeded",
            "invocation_shape_limit_exceeded",
            "shape_product_overflow",
            "instance_schema_failed",
            "schema_evaluator_failed",
        ]
    },
}
_CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_ID,
    **_closed_object(_ATTEMPT_PROPERTIES),
    "allOf": [
        {
            "oneOf": [
                {
                    "properties": {
                        "attempt_status": {"const": "reservation_rejected"},
                        "attempted_shape_units": {"type": "null"},
                        "aggregate_after_reservation": {"type": "null"},
                        "evaluator_invoked": {"const": False},
                        "evaluation_passed": {"type": "null"},
                        "failure_code": {
                            "enum": [
                                "per_evaluation_limit_exceeded",
                                "invocation_shape_limit_exceeded",
                                "shape_product_overflow",
                            ]
                        },
                    }
                },
                {
                    "properties": {
                        "attempt_status": {"const": "evaluation_completed"},
                        "attempted_shape_units": {"type": "integer"},
                        "aggregate_after_reservation": {"type": "integer"},
                        "evaluator_invoked": {"const": True},
                        "evaluation_passed": {"type": "boolean"},
                        "failure_code": {
                            "enum": [None, "instance_schema_failed"]
                        },
                    },
                    "oneOf": [
                        {
                            "properties": {
                                "evaluation_passed": {"const": True},
                                "failure_code": {"type": "null"},
                            }
                        },
                        {
                            "properties": {
                                "evaluation_passed": {"const": False},
                                "failure_code": {
                                    "const": "instance_schema_failed"
                                },
                            }
                        },
                    ],
                },
                {
                    "properties": {
                        "attempt_status": {"const": "evaluator_failed"},
                        "attempted_shape_units": {"type": "integer"},
                        "aggregate_after_reservation": {"type": "integer"},
                        "evaluator_invoked": {"const": True},
                        "evaluation_passed": {"type": "null"},
                        "failure_code": {"const": "schema_evaluator_failed"},
                    }
                },
            ]
        }
    ],
}

_CONFORMANCE_COMPLETENESS_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": CONFORMANCE_COMPLETENESS_SCHEMA_ID,
    **_closed_object(
        {
            "required_case_count": {"type": "integer", "minimum": 0},
            "result_row_count": {"type": "integer", "minimum": 0},
            "missing_case_ids": {
                "type": "array",
                "items": _MACHINE_ID,
            },
            "extra_case_ids": {
                "type": "array",
                "items": _MACHINE_ID,
            },
            "duplicate_case_ids": {
                "type": "array",
                "items": _MACHINE_ID,
            },
            "case_kind_mismatch_ids": {
                "type": "array",
                "items": _MACHINE_ID,
            },
            "case_fingerprint_mismatch_ids": {
                "type": "array",
                "items": _MACHINE_ID,
            },
            "complete": {"type": "boolean"},
        }
    ),
}

_EXPECTED_PUBLISHED_IDENTITY = {
    "properties": {
        "expected_result_kind": {"const": "published_report"},
        "expected_report_schema_id": _MACHINE_ID,
        "expected_result_fingerprint": _FINGERPRINT,
        "expected_control_failure_stage": {"type": "null"},
        "expected_control_failure_code": {"type": "null"},
        "expected_control_failure_artifact_role": {"type": "null"},
    }
}
_EXPECTED_CONTROL_IDENTITY = {
    "properties": {
        "expected_result_kind": {"const": "control_failure"},
        "expected_report_schema_id": {"type": "null"},
        "expected_result_fingerprint": {"type": "null"},
        "expected_control_failure_stage": {
            "enum": ["preflight", "validation"]
        },
        "expected_control_failure_code": _MACHINE_ID,
        "expected_control_failure_artifact_role": _MACHINE_ID,
    }
}
_ACTUAL_PUBLISHED_IDENTITY = {
    "properties": {
        "actual_result_kind": {"const": "published_report"},
        "actual_report_schema_id": _MACHINE_ID,
        "actual_result_fingerprint": _FINGERPRINT,
        "actual_control_failure_stage": {"type": "null"},
        "actual_control_failure_code": {"type": "null"},
        "actual_control_failure_artifact_role": {"type": "null"},
    }
}
_ACTUAL_CONTROL_IDENTITY = {
    "properties": {
        "actual_result_kind": {"const": "control_failure"},
        "actual_report_schema_id": {"type": "null"},
        "actual_result_fingerprint": {"type": "null"},
        "actual_control_failure_stage": {
            "enum": ["preflight", "validation"]
        },
        "actual_control_failure_code": _MACHINE_ID,
        "actual_control_failure_artifact_role": _MACHINE_ID,
    }
}
_ACTUAL_UNAVAILABLE_IDENTITY = {
    "properties": {
        "actual_result_kind": {"const": "unavailable"},
        "actual_report_schema_id": {"type": "null"},
        "actual_result_fingerprint": {"type": "null"},
        "actual_control_failure_stage": {"type": "null"},
        "actual_control_failure_code": {"type": "null"},
        "actual_control_failure_artifact_role": {"type": "null"},
    }
}

_FIXTURE_CASE_RESULT = {
    **_closed_object(
        {
            "expected_result_kind": {
                "enum": ["published_report", "control_failure"]
            },
            "expected_report_schema_id": _NULLABLE_MACHINE_ID,
            "expected_result_fingerprint": _NULLABLE_FINGERPRINT,
            "expected_control_failure_stage": {
                "type": ["string", "null"]
            },
            "expected_control_failure_code": _NULLABLE_MACHINE_ID,
            "expected_control_failure_artifact_role": _NULLABLE_MACHINE_ID,
            "actual_result_kind": {
                "enum": [
                    "published_report",
                    "control_failure",
                    "unavailable",
                ]
            },
            "actual_report_schema_id": _NULLABLE_MACHINE_ID,
            "actual_result_fingerprint": _NULLABLE_FINGERPRINT,
            "actual_control_failure_stage": {"type": ["string", "null"]},
            "actual_control_failure_code": _NULLABLE_MACHINE_ID,
            "actual_control_failure_artifact_role": _NULLABLE_MACHINE_ID,
            "result_identity_matches": {"type": "boolean"},
        }
    ),
    "allOf": [
        {
            "oneOf": [
                _EXPECTED_PUBLISHED_IDENTITY,
                _EXPECTED_CONTROL_IDENTITY,
            ]
        },
        {
            "oneOf": [
                _ACTUAL_PUBLISHED_IDENTITY,
                _ACTUAL_CONTROL_IDENTITY,
                _ACTUAL_UNAVAILABLE_IDENTITY,
            ]
        },
        {
            "oneOf": [
                {
                    "properties": {
                        "expected_result_kind": {"const": "published_report"},
                        "actual_result_kind": {"const": "published_report"},
                    }
                },
                {
                    "properties": {
                        "expected_result_kind": {"const": "control_failure"},
                        "actual_result_kind": {"const": "control_failure"},
                    }
                },
                {
                    "properties": {
                        "expected_result_kind": {"const": "published_report"},
                        "actual_result_kind": {"const": "control_failure"},
                        "result_identity_matches": {"const": False},
                    }
                },
                {
                    "properties": {
                        "expected_result_kind": {"const": "published_report"},
                        "actual_result_kind": {"const": "unavailable"},
                        "result_identity_matches": {"const": False},
                    }
                },
                {
                    "properties": {
                        "expected_result_kind": {"const": "control_failure"},
                        "actual_result_kind": {"const": "published_report"},
                        "result_identity_matches": {"const": False},
                    }
                },
                {
                    "properties": {
                        "expected_result_kind": {"const": "control_failure"},
                        "actual_result_kind": {"const": "unavailable"},
                        "result_identity_matches": {"const": False},
                    }
                },
            ]
        },
    ],
}
_RESULT_ROW_PROPERTIES = {
    "result_index": {"type": "integer", "minimum": 0},
    "case_id": _MACHINE_ID,
    "case_kind": {"enum": ["core_schema_positive", "semantic_fixture"]},
    "case_fingerprint": _FINGERPRINT,
    "outcome": {"enum": ["passed", "failed"]},
    "schema_case_result": {
        "anyOf": [
            _closed_object(
                {"instance_schema_valid": {"type": ["boolean", "null"]}}
            ),
            {"type": "null"},
        ]
    },
    "fixture_case_result": {
        "anyOf": [_FIXTURE_CASE_RESULT, {"type": "null"}]
    },
    "schema_evaluations": {
        "type": "array",
        "items": {
            key: value
            for key, value in _CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_HOST.items()
            if key not in ("$schema", "$id")
        },
    },
    "aggregate_schema_evaluation_shape_units": {
        "type": "integer",
        "minimum": 0,
    },
    "invocation_shape_limit": {"const": 16_000_000},
    "within_every_per_evaluation_limit": {"type": "boolean"},
    "within_invocation_limit": {"type": "boolean"},
    "failure_code": {
        "enum": [
            None,
            "case_content_unavailable",
            "case_fingerprint_mismatch",
            "case_execution_failed",
            "schema_evaluation_failed",
            "validation_budget_exceeded",
        ]
    },
}
_RESULT_ROW = {
    **_closed_object(_RESULT_ROW_PROPERTIES),
    "allOf": [
        {
            "oneOf": [
                {
                    "properties": {
                        "case_kind": {"const": "core_schema_positive"},
                        "schema_case_result": {"type": "object"},
                        "fixture_case_result": {"type": "null"},
                    }
                },
                {
                    "properties": {
                        "case_kind": {"const": "semantic_fixture"},
                        "schema_case_result": {"type": "null"},
                        "fixture_case_result": {
                            "anyOf": [
                                _FIXTURE_CASE_RESULT,
                                {"type": "null"},
                            ]
                        },
                    }
                },
            ]
        }
    ],
}
_CAMPAIGN_INTEGRITY = _closed_object(
    {
        "program_binding_matches": {"type": "boolean"},
        "gate_profile_binding_matches": {"type": "boolean"},
        "core_schema_coverage_matches_program": {"type": "boolean"},
        "missing_core_schema_case_ids": {
            "type": "array",
            "items": _MACHINE_ID,
        },
        "extra_core_schema_case_ids": {
            "type": "array",
            "items": _MACHINE_ID,
        },
        "failure_codes": {
            "type": "array",
            "items": {
                "enum": [
                    "campaign_program_binding_mismatch",
                    "campaign_gate_profile_binding_mismatch",
                    "campaign_core_schema_coverage_missing",
                    "campaign_core_schema_coverage_extra",
                ]
            },
        },
        "passed": {"type": "boolean"},
    }
)
_REPORT_GATE = _closed_object(
    {
        "gate_profile_id": _MACHINE_ID,
        "gate_profile_version": _MACHINE_ID,
        "gate_implementation_fingerprint": _FINGERPRINT,
        "budget_profile": _MACHINE_ID,
        "limits_fingerprint": _FINGERPRINT,
        "campaign_input_byte_limit": {"const": 4_194_304},
        "referenced_case_content_byte_limit": {"const": 4_194_304},
        "gate_profile_fingerprint": _FINGERPRINT,
    }
)
_CONFORMANCE_REPORT_SCHEMA_HOST = {
    "$schema": _DRAFT,
    "$id": CONFORMANCE_REPORT_SCHEMA_ID,
    **_closed_object(
        {
            "schema": {"const": CONFORMANCE_REPORT_SCHEMA_ID},
            "program_id": _MACHINE_ID,
            "program_fingerprint": _FINGERPRINT,
            "campaign_id": _MACHINE_ID,
            "campaign_fingerprint": _FINGERPRINT,
            "required_case_set_fingerprint": _FINGERPRINT,
            "gate": _REPORT_GATE,
            "campaign_integrity": _CAMPAIGN_INTEGRITY,
            "result_rows": {
                "type": "array",
                "items": _RESULT_ROW,
            },
            "completeness": {
                key: value
                for key, value in _CONFORMANCE_COMPLETENESS_SCHEMA_HOST.items()
                if key not in ("$schema", "$id")
            },
            "all_case_outcomes_passed": {"type": "boolean"},
            "decision": {"enum": ["passed", "failed"]},
            "report_fingerprint": _FINGERPRINT,
        }
    ),
}

PROGRAM_MANIFEST_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_PROGRAM_MANIFEST_SCHEMA_HOST))
)
TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_TRUSTED_ASSEMBLER_SCHEMA_HOST))
)
CONFORMANCE_GATE_PROFILE_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_CONFORMANCE_GATE_PROFILE_SCHEMA_HOST))
)
CONFORMANCE_CAMPAIGN_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_CONFORMANCE_CAMPAIGN_SCHEMA_HOST))
)
CONFORMANCE_FIXTURE_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_CONFORMANCE_FIXTURE_SCHEMA_HOST))
)
CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_HOST))
)
CONFORMANCE_COMPLETENESS_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_CONFORMANCE_COMPLETENESS_SCHEMA_HOST))
)
CONFORMANCE_REPORT_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_CONFORMANCE_REPORT_SCHEMA_HOST))
)
if type(PROGRAM_MANIFEST_SCHEMA) is not JsonObject:
    raise AssertionError("program manifest schema must be an owned object")
if type(TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA) is not JsonObject:
    raise AssertionError("assembler profile schema must be an owned object")
for _schema_name, _schema_value in (
    ("conformance gate profile", CONFORMANCE_GATE_PROFILE_SCHEMA),
    ("conformance campaign", CONFORMANCE_CAMPAIGN_SCHEMA),
    ("conformance fixture", CONFORMANCE_FIXTURE_SCHEMA),
    ("conformance attempt row", CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA),
    ("conformance completeness", CONFORMANCE_COMPLETENESS_SCHEMA),
    ("conformance report", CONFORMANCE_REPORT_SCHEMA),
):
    if type(_schema_value) is not JsonObject:
        raise AssertionError(f"{_schema_name} schema must be an owned object")

PROGRAM_MANIFEST_SCHEMA_FINGERPRINT = canonical_fingerprint(
    PROGRAM_MANIFEST_SCHEMA
)
TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_FINGERPRINT = canonical_fingerprint(
    TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA
)
CONFORMANCE_GATE_PROFILE_SCHEMA_FINGERPRINT = canonical_fingerprint(
    CONFORMANCE_GATE_PROFILE_SCHEMA
)
CONFORMANCE_CAMPAIGN_SCHEMA_FINGERPRINT = canonical_fingerprint(
    CONFORMANCE_CAMPAIGN_SCHEMA
)
CONFORMANCE_FIXTURE_SCHEMA_FINGERPRINT = canonical_fingerprint(
    CONFORMANCE_FIXTURE_SCHEMA
)
CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_FINGERPRINT = canonical_fingerprint(
    CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA
)
CONFORMANCE_COMPLETENESS_SCHEMA_FINGERPRINT = canonical_fingerprint(
    CONFORMANCE_COMPLETENESS_SCHEMA
)
CONFORMANCE_REPORT_SCHEMA_FINGERPRINT = canonical_fingerprint(
    CONFORMANCE_REPORT_SCHEMA
)


__all__ = (
    "BUDGET_RECEIPT_NESTED_FIELD_COUNT",
    "CONFORMANCE_CAMPAIGN_SCHEMA",
    "CONFORMANCE_CAMPAIGN_SCHEMA_FINGERPRINT",
    "CONFORMANCE_CAMPAIGN_SCHEMA_ID",
    "CONFORMANCE_COMPLETENESS_SCHEMA",
    "CONFORMANCE_COMPLETENESS_SCHEMA_FINGERPRINT",
    "CONFORMANCE_COMPLETENESS_SCHEMA_ID",
    "CONFORMANCE_FIXTURE_SCHEMA",
    "CONFORMANCE_FIXTURE_SCHEMA_FINGERPRINT",
    "CONFORMANCE_FIXTURE_SCHEMA_ID",
    "CONFORMANCE_GATE_PROFILE_SCHEMA",
    "CONFORMANCE_GATE_PROFILE_SCHEMA_FINGERPRINT",
    "CONFORMANCE_GATE_PROFILE_SCHEMA_ID",
    "CONFORMANCE_REPORT_SCHEMA",
    "CONFORMANCE_REPORT_SCHEMA_FINGERPRINT",
    "CONFORMANCE_REPORT_SCHEMA_ID",
    "CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA",
    "CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_FINGERPRINT",
    "CONFORMANCE_SCHEMA_ATTEMPT_ROW_SCHEMA_ID",
    "FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT",
    "KERNEL_OWNED_REPORT_PATHS",
    "KERNEL_REPORT_FIELD_ROLES",
    "PROGRAM_MANIFEST_SCHEMA",
    "PROGRAM_MANIFEST_SCHEMA_FINGERPRINT",
    "PROGRAM_MANIFEST_SCHEMA_ID",
    "REPORT_BUDGET_RECEIPT_PATH",
    "REPORT_FINGERPRINT_PATH",
    "TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA",
    "TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_FINGERPRINT",
    "TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID",
)
