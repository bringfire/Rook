using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Rook.Artifacts;

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
/// Validates a <see cref="ReconstructionViewSetRequest"/> against the artifact store, copies
/// source blobs into a new <c>reconstruction_view_set</c> artifact, and builds the outcome envelope.
/// All hard rejects return before any <c>store.Create</c> call — no artifact is written on failure.
/// </summary>
public sealed class ReconstructionViewSetAssembler : IReconstructionViewSetAssembler
{
    // Role pattern mirrors ArtifactStore's internal RolePattern.
    private static readonly Regex RolePattern = new(@"^[a-z0-9][a-z0-9_-]*$", RegexOptions.Compiled);

    private readonly ArtifactStore _store;

    public ReconstructionViewSetAssembler(ArtifactStore store)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
    }

    public ReconstructionViewSetOutcome Assemble(ReconstructionViewSetRequest request)
    {
        if (request is null) throw new ArgumentNullException(nameof(request));

        // ── 1. Resolve slotsExpected ─────────────────────────────────────────
        var slotsExpected = (IReadOnlyList<string>)(request.SlotsExpected ?? ReconstructionViewSlots.Canonical);

        // ── 2. Validate slotsExpected: each ∈ Allowed, no duplicates ────────
        var seenExpected = new HashSet<string>(StringComparer.Ordinal);
        foreach (var expectedSlot in slotsExpected)
        {
            if (!ReconstructionViewSlots.Allowed.Contains(expectedSlot))
                return Fail("invalid_view_set", $"'slots_expected' contains unknown slot '{expectedSlot}'.", "slots_expected", "unknown_slot");
            if (!seenExpected.Add(expectedSlot))
                return Fail("invalid_view_set", $"'slots_expected' contains duplicate slot '{expectedSlot}'.", "slots_expected", "duplicate_slot");
        }

        // ── 3. Validate views (guard: assembler defends against empty too) ──
        if (request.Views is null || request.Views.Count == 0)
            return Fail("invalid_view_set", "views must be a non-empty array.", "views", "empty_views");

        // Per-view validation: collect blob inputs as we go.
        // All rejects must happen BEFORE store.Create (step 9).
        var blobs = new List<BlobInput>(request.Views.Count);
        var viewRows = new List<IReadOnlyDictionary<string, object?>>(request.Views.Count);
        var slotsPresent = new List<string>(request.Views.Count);
        var seenSlots = new HashSet<string>(StringComparer.Ordinal);
        var parentIdSet = new LinkedList<Guid>();  // insertion-ordered dedup
        var parentIdSeen = new HashSet<Guid>();

        foreach (var view in request.Views)
        {
            var slot = view.Slot;

            // slot ∈ Allowed
            if (!ReconstructionViewSlots.Allowed.Contains(slot))
                return Fail("invalid_view_set", $"Unknown slot '{slot}'.", slot, "unknown_slot");

            // no duplicate slot across views
            if (!seenSlots.Add(slot))
                return Fail("invalid_view_set", $"Duplicate slot '{slot}'.", slot, "duplicate_slot");

            // resolve role (null => "image")
            var role = view.Role ?? "image";

            // role matches pattern
            if (!RolePattern.IsMatch(role))
                return Fail("invalid_source_role", $"Role '{role}' does not match required pattern.", slot, "invalid_role_format");

            // source artifact exists
            var artifact = _store.Get(view.ArtifactId);
            if (artifact is null)
                return Fail("invalid_source_artifact", $"Source artifact '{view.ArtifactId:D}' not found.", slot, "source_not_found");

            // source kind ∈ AssemblySourceKinds
            if (!ReconstructionViewSlots.AssemblySourceKinds.Contains(artifact.Kind))
                return Fail("invalid_source_artifact", $"Source artifact kind '{artifact.Kind}' is not image-capable.", slot, "source_kind_not_image");

            // role present on artifact
            if (!artifact.Files.Any(f => string.Equals(f.Role, role, StringComparison.Ordinal)))
                return Fail("invalid_source_role", $"Role '{role}' not present on artifact '{view.ArtifactId:D}'.", slot, "role_not_present");

            // ── 4. Resolve bytes ─────────────────────────────────────────────
            byte[] bytes;
            string ext;
            try
            {
                var path = _store.GetBlobAbsolutePath(view.ArtifactId, role);
                bytes = File.ReadAllBytes(path);
                ext = Path.GetExtension(path).TrimStart('.');
                if (string.IsNullOrEmpty(ext)) ext = "bin";
            }
            catch (Exception ex)
            {
                return Fail("invalid_source_artifact",
                    $"Source blob for slot '{slot}' could not be read: {ex.Message}", slot, "source_blob_unreadable");
            }

            // ── 5. Build BlobInput ───────────────────────────────────────────
            var viewRole = ReconstructionViewSlots.FileRole(slot);
            blobs.Add(new BlobInput(viewRole, bytes, ext));
            slotsPresent.Add(slot);

            // track parent ids (distinct, insertion order)
            if (parentIdSeen.Add(view.ArtifactId))
                parentIdSet.AddLast(view.ArtifactId);

            // ── build view row (mirrors metadata views array) ────────────────
            var row = new Dictionary<string, object?>(StringComparer.Ordinal)
            {
                ["slot"] = slot,
                ["source_artifact_id"] = view.ArtifactId.ToString("D"),
                ["source_role"] = role,
                ["view_role"] = viewRole,
            };
            if (view.Provenance is not null)
                row["provenance"] = view.Provenance.DeepClone() as JsonObject;
            viewRows.Add(row);
        }

        // ── 6. Compute complete ──────────────────────────────────────────────
        var slotsPresentSet = new HashSet<string>(slotsPresent, StringComparer.Ordinal);
        var complete = slotsExpected.All(s => slotsPresentSet.Contains(s));

        // ── 7. Build metadata ────────────────────────────────────────────────
        var slotsExpectedArray = new JsonArray();
        foreach (var s in slotsExpected) slotsExpectedArray.Add(JsonValue.Create(s));

        var slotsPresentArray = new JsonArray();
        foreach (var s in slotsPresent) slotsPresentArray.Add(JsonValue.Create(s));

        var metaViewsArray = new JsonArray();
        foreach (var row in viewRows)
        {
            var metaView = new JsonObject
            {
                ["slot"] = JsonValue.Create((string)row["slot"]!),
                ["source_artifact_id"] = JsonValue.Create((string)row["source_artifact_id"]!),
                ["source_role"] = JsonValue.Create((string)row["source_role"]!),
                ["view_role"] = JsonValue.Create((string)row["view_role"]!),
            };
            if (row.ContainsKey("provenance") && row["provenance"] is JsonObject prov)
                metaView["provenance"] = prov.DeepClone();
            metaViewsArray.Add(metaView);
        }

        var metadata = new Dictionary<string, JsonNode?>
        {
            ["method"] = JsonValue.Create(request.Method ?? "manual_assembly"),
            ["slots_expected"] = slotsExpectedArray,
            ["slots_present"] = slotsPresentArray,
            ["complete"] = JsonValue.Create(complete),
            ["views"] = metaViewsArray,
        };
        if (request.Note is not null)
            metadata["note"] = JsonValue.Create(request.Note);

        // ── 8+9. parentIds + store.Create ───────────────────────────────────
        var parentIds = new List<Guid>(parentIdSet);

        // ── 9. Write artifact ────────────────────────────────────────────────
        var artifact2 = _store.Create(
            ReconstructionArtifactKinds.ViewSet,
            blobs,
            parentIds,
            metadata);

        // ── 10. Return outcome ───────────────────────────────────────────────
        return new ReconstructionViewSetOutcome(
            true,
            artifact2,
            slotsExpected,
            slotsPresent,
            complete,
            viewRows,
            null);
    }

    private static ReconstructionViewSetOutcome Fail(string code, string message, string? field, string reason)
    {
        var failure = new ReconstructionFailure(
            code,
            message,
            false,
            field,
            new Dictionary<string, object?> { ["reason"] = reason });
        return new ReconstructionViewSetOutcome(
            false,
            null,
            Array.Empty<string>(),
            Array.Empty<string>(),
            false,
            Array.Empty<IReadOnlyDictionary<string, object?>>(),
            failure);
    }
}
