using System;
using System.Collections.Generic;

namespace Rook.Services.Reconstruction;

public interface IReconstructionViewSetAssembler
{
    // Pure synchronous artifact transform. Never writes to the job ledger.
    ReconstructionViewSetOutcome Assemble(ReconstructionViewSetRequest request);
}

// Result envelope. Defined in full here so the type is stable across Tasks 1-3.
// Task 1: spy returns empty Views. Task 2: assembler populates Artifact + Views.
// Task 3: handler serializes Views directly (no record change mid-plan).
public sealed record ReconstructionViewSetOutcome(
    bool Success,
    Rook.Artifacts.Artifact? Artifact,
    IReadOnlyList<string> SlotsExpected,
    IReadOnlyList<string> SlotsPresent,
    bool Complete,
    // Per-view response rows: {slot, source_artifact_id, source_role, view_role, provenance?}
    IReadOnlyList<IReadOnlyDictionary<string, object?>> Views,
    ReconstructionFailure? Failure);

/// <summary>
/// Temporary stub. Task 2 replaces this entire class with the real ReconstructionViewSetAssembler.
/// Task 4 greps to confirm the Default class is gone.
/// </summary>
public sealed class DefaultReconstructionViewSetAssembler : IReconstructionViewSetAssembler
{
    public ReconstructionViewSetOutcome Assemble(ReconstructionViewSetRequest request)
        => new(
            false,
            null,
            Array.Empty<string>(),
            Array.Empty<string>(),
            false,
            Array.Empty<IReadOnlyDictionary<string, object?>>(),
            new ReconstructionFailure(
                "execution_failed",
                "View-set assembler not yet implemented.",
                false,
                null,
                new Dictionary<string, object?>()));
}
