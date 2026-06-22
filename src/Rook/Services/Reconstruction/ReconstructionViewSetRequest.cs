using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

/// <summary>
/// Stable request DTO for the assemble_view_set op.
/// TryParse is added in Task 2. Empty is the sentinel used by the Task 1 placeholder.
/// </summary>
public sealed record ReconstructionViewSetRequest(
    IReadOnlyList<string>? SlotsExpected,   // null = omitted (=> canonical four); empty = explicit (=> reject in Task 2)
    IReadOnlyList<ViewBinding> Views,
    string? Method,
    string? Note)
{
    public static readonly ReconstructionViewSetRequest Empty = new(null, Array.Empty<ViewBinding>(), null, null);
}

public sealed record ViewBinding(
    string Slot,
    Guid ArtifactId,
    string? Role,                  // null => "image"
    JsonObject? Provenance);
