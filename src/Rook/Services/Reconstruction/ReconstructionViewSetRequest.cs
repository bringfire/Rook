using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

/// <summary>
/// Stable request DTO for the assemble_view_set op.
/// Empty is the sentinel used by the Task 1 placeholder.
/// </summary>
public sealed record ReconstructionViewSetRequest(
    IReadOnlyList<string>? SlotsExpected,   // null = omitted (=> canonical four); empty = explicit (=> reject)
    IReadOnlyList<ViewBinding> Views,
    string? Method,
    string? Note)
{
    public static readonly ReconstructionViewSetRequest Empty = new(null, Array.Empty<ViewBinding>(), null, null);

    /// <summary>
    /// Parses a JSON request body into a typed DTO, or returns null with a failure reason.
    /// Owns structural/shape rejects only — semantic (slot-vocabulary, store-artifact) checks
    /// belong to the assembler.
    /// </summary>
    public static ReconstructionViewSetRequest? TryParse(string? body, out ReconstructionFailure? failure)
    {
        if (string.IsNullOrWhiteSpace(body))
        {
            failure = Fail("invalid_view_set", "Request body is empty.", null, "empty_body");
            return null;
        }

        JsonNode? root;
        try
        {
            root = JsonNode.Parse(body);
        }
        catch
        {
            failure = Fail("invalid_view_set", "Request body is not valid JSON.", null, "invalid_json");
            return null;
        }

        if (root is not JsonObject obj)
        {
            failure = Fail("invalid_view_set", "Request body must be a JSON object.", null, "not_object");
            return null;
        }

        // ── views ────────────────────────────────────────────────────────────
        if (!obj.TryGetPropertyValue("views", out var viewsNode)
            || viewsNode is null
            || viewsNode is not JsonArray viewsArray
            || viewsArray.Count == 0)
        {
            failure = Fail("invalid_view_set", "views must be a non-empty array.", "views", "empty_views");
            return null;
        }

        var views = new List<ViewBinding>();
        foreach (var viewNode in viewsArray)
        {
            if (viewNode is not JsonObject viewObj)
            {
                failure = Fail("invalid_view_set", "Each view must be a JSON object.", "views", "view_not_object");
                return null;
            }

            // slot (required, string)
            if (!viewObj.TryGetPropertyValue("slot", out var slotNode)
                || slotNode is null)
            {
                failure = Fail("invalid_view_set", "Each view must have a 'slot' field.", "views", "missing_slot");
                return null;
            }
            string slot;
            try { slot = slotNode.GetValue<string>(); }
            catch
            {
                failure = Fail("invalid_view_set", "'slot' must be a string.", "views", "non_string_slot");
                return null;
            }

            // artifact_id (required, guid)
            if (!viewObj.TryGetPropertyValue("artifact_id", out var artifactIdNode)
                || artifactIdNode is null)
            {
                failure = Fail("invalid_view_set", "Each view must have an 'artifact_id' field.", "views", "missing_artifact_id");
                return null;
            }
            string artifactIdStr;
            try { artifactIdStr = artifactIdNode.GetValue<string>(); }
            catch
            {
                failure = Fail("invalid_view_set", "'artifact_id' must be a string GUID.", "views", "non_string_artifact_id");
                return null;
            }
            if (!Guid.TryParseExact(artifactIdStr, "D", out var artifactId)
                && !Guid.TryParse(artifactIdStr, out artifactId))
            {
                failure = Fail("invalid_view_set", $"'artifact_id' '{artifactIdStr}' is not a valid GUID.", "views", "invalid_artifact_id");
                return null;
            }

            // role (optional, string)
            string? role = null;
            if (viewObj.TryGetPropertyValue("role", out var roleNode) && roleNode is not null)
            {
                try { role = roleNode.GetValue<string>(); }
                catch
                {
                    failure = Fail("invalid_view_set", "'role' must be a string.", "views", "non_string_role");
                    return null;
                }
            }

            // provenance (optional, must be JsonObject if present)
            JsonObject? provenance = null;
            if (viewObj.TryGetPropertyValue("provenance", out var provNode) && provNode is not null)
            {
                if (provNode is not JsonObject provObj)
                {
                    failure = Fail("invalid_provenance", "'provenance' must be a JSON object.", "views", "provenance_not_object");
                    return null;
                }
                provenance = (JsonObject)provObj.DeepClone();
            }

            views.Add(new ViewBinding(slot, artifactId, role, provenance));
        }

        // ── slots_expected (optional, but if present must be non-empty array of strings) ──
        IReadOnlyList<string>? slotsExpected = null;
        if (obj.TryGetPropertyValue("slots_expected", out var slotsNode) && slotsNode is not null)
        {
            if (slotsNode is not JsonArray slotsArray)
            {
                failure = Fail("invalid_view_set", "'slots_expected' must be an array.", "slots_expected", "non_array_slots_expected");
                return null;
            }
            if (slotsArray.Count == 0)
            {
                failure = Fail("invalid_view_set", "'slots_expected' must not be empty; omit it to use the canonical four.", "slots_expected", "empty_slots_expected");
                return null;
            }
            var slotsList = new List<string>();
            foreach (var slotNode in slotsArray)
            {
                if (slotNode is null)
                {
                    failure = Fail("invalid_view_set", "'slots_expected' must be a string array.", "slots_expected", "null_slot");
                    return null;
                }
                string s;
                try { s = slotNode.GetValue<string>(); }
                catch
                {
                    failure = Fail("invalid_view_set", "'slots_expected' must be a string array.", "slots_expected", "non_string_slot");
                    return null;
                }
                slotsList.Add(s);
            }
            slotsExpected = slotsList;
        }

        // ── method (optional, string) ──────────────────────────────────────
        string? method = null;
        if (obj.TryGetPropertyValue("method", out var methodNode) && methodNode is not null)
        {
            try { method = methodNode.GetValue<string>(); }
            catch
            {
                failure = Fail("invalid_view_set", "'method' must be a string.", "method", "non_string_method");
                return null;
            }
        }

        // ── note (optional, string) ────────────────────────────────────────
        string? note = null;
        if (obj.TryGetPropertyValue("note", out var noteNode) && noteNode is not null)
        {
            try { note = noteNode.GetValue<string>(); }
            catch
            {
                failure = Fail("invalid_view_set", "'note' must be a string.", "note", "non_string_note");
                return null;
            }
        }

        failure = null;
        return new ReconstructionViewSetRequest(slotsExpected, views, method, note);
    }

    private static ReconstructionFailure Fail(string code, string message, string? field, string reason)
        => new(code, message, false, field, new Dictionary<string, object?> { ["reason"] = reason });
}

public sealed record ViewBinding(
    string Slot,
    Guid ArtifactId,
    string? Role,                  // null => "image"
    JsonObject? Provenance);
