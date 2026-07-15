"""Model-free validation kernel public boundary."""

from .api import ValidationResult, validate_artifacts
from .control import BudgetExceededFailure, ValidationControlFailure
from .conformance import (
    ConformanceGateInvocationFailure,
    SealedConformanceGateProfile,
    TrustedConformanceFixtureContext,
    TrustedConformanceGateResult,
    run_conformance_gate,
    seal_conformance_gate_profile,
)
from .invocation import (
    SealedTrustedBundleAssemblerProfile,
    TrustedValidationBundleInput,
    issue_trusted_validation_bundle,
    seal_trusted_bundle_assembler_profile,
)
from .program import SealedValidationProgram, compose_and_seal_program
from .reporting import PublishedValidationReport

__all__ = (
    "ValidationResult",
    "validate_artifacts",
    "ValidationControlFailure",
    "BudgetExceededFailure",
    "PublishedValidationReport",
    "SealedValidationProgram",
    "compose_and_seal_program",
    "SealedTrustedBundleAssemblerProfile",
    "seal_trusted_bundle_assembler_profile",
    "TrustedValidationBundleInput",
    "issue_trusted_validation_bundle",
    "ConformanceGateInvocationFailure",
    "SealedConformanceGateProfile",
    "seal_conformance_gate_profile",
    "TrustedConformanceFixtureContext",
    "TrustedConformanceGateResult",
    "run_conformance_gate",
)
