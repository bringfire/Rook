"""Fixed bootstrap schemas owned by the validation kernel seal."""

from __future__ import annotations

import json

from .canonical_json import canonical_fingerprint
from .owned_json import JsonObject, own_trusted_json


PROGRAM_MANIFEST_SCHEMA_ID = "rook.validation_program_manifest:v1"
TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_ID = (
    "rook.trusted_bundle_assembler_profile:v1"
)
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

PROGRAM_MANIFEST_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_PROGRAM_MANIFEST_SCHEMA_HOST))
)
TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA = own_trusted_json(
    json.loads(json.dumps(_TRUSTED_ASSEMBLER_SCHEMA_HOST))
)
if type(PROGRAM_MANIFEST_SCHEMA) is not JsonObject:
    raise AssertionError("program manifest schema must be an owned object")
if type(TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA) is not JsonObject:
    raise AssertionError("assembler profile schema must be an owned object")

PROGRAM_MANIFEST_SCHEMA_FINGERPRINT = canonical_fingerprint(
    PROGRAM_MANIFEST_SCHEMA
)
TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA_FINGERPRINT = canonical_fingerprint(
    TRUSTED_BUNDLE_ASSEMBLER_PROFILE_SCHEMA
)


__all__ = (
    "BUDGET_RECEIPT_NESTED_FIELD_COUNT",
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
