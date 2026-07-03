using System;
using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Text.Json;

namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorExtractor : ICanvasDirectorExtractor
    {
        private const string ExportMetadataKind = "rook.canvas_director.export";
        private const string TemporaryExportNickNamePrefix = "CanvasDirector Export:";

        public CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request)
        {
            ValidateSolveMode(
                request.SolveMode ?? string.Empty,
                request.ExpectedSolutionToken,
                supportsReuseVerification: false);

            var document = ResolveActiveGrasshopperDocument();
            ValidateDocumentIdentity(document, request);
            ApplySolveMode(document, request);
            var payload = TryExtractFromDocument(document, request);
            return ParseExportPayload(payload, request);
        }

        internal static void ValidateSolveMode(
            string solveMode,
            string? expectedSolutionToken,
            bool supportsReuseVerification)
        {
            if (string.Equals(solveMode, "require_fresh_solve", StringComparison.Ordinal))
            {
                return;
            }

            if (string.Equals(solveMode, "reuse_verified_solution", StringComparison.Ordinal))
            {
                if (string.IsNullOrWhiteSpace(expectedSolutionToken))
                {
                    throw new CanvasDirectorException(
                        "freshness_token_required",
                        "CanvasDirector reuse_verified_solution requires expected_solution_token.",
                        400);
                }

                if (!supportsReuseVerification)
                {
                    throw new CanvasDirectorException(
                        "unsupported_solve_mode",
                        "CanvasDirector reuse verification is not supported by this extraction bridge.",
                        400);
                }

                return;
            }

            throw new CanvasDirectorException(
                "unsupported_solve_mode",
                $"Unsupported CanvasDirector solve_mode '{solveMode}'.",
                400);
        }

        internal static void ApplySolveMode(object document, CanvasDirectorExtractRequest request)
        {
            if (string.Equals(request.SolveMode, "require_fresh_solve", StringComparison.Ordinal))
            {
                RequireFreshSolve(document);
                return;
            }

            ValidateSolveMode(
                request.SolveMode ?? string.Empty,
                request.ExpectedSolutionToken,
                supportsReuseVerification: false);
        }

        internal static void RequireFreshSolve(object document)
        {
            if (ReadIntProperty(document, "SolutionDepth") is int solutionDepth && solutionDepth > 0)
            {
                throw new CanvasDirectorException(
                    "solve_locked",
                    "CanvasDirector cannot start a fresh solve while Grasshopper is already solving.",
                    409);
            }

            var beforeToken = ReadSolutionToken(document);
            if (beforeToken == null)
            {
                throw new CanvasDirectorException(
                    "solve_failed",
                    "CanvasDirector could not read the Grasshopper solution token before solving.",
                    503);
            }

            var newSolution = document.GetType().GetMethod(
                "NewSolution",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                binder: null,
                types: new[] { typeof(bool) },
                modifiers: null);

            if (newSolution == null)
            {
                throw new CanvasDirectorException(
                    "solve_failed",
                    "CanvasDirector could not find Grasshopper document NewSolution(bool).",
                    503);
            }

            try
            {
                // First slice uses guarded synchronous solve on the UI thread. Do not ScheduleSolution
                // and block inside this sync bridge, because that can self-deadlock.
                newSolution.Invoke(document, new object[] { true });
            }
            catch (TargetInvocationException ex)
            {
                var message = ex.InnerException?.Message ?? ex.Message;
                throw new CanvasDirectorException(
                    "solve_failed",
                    $"CanvasDirector Grasshopper solve failed: {message}",
                    503);
            }
            catch (Exception ex) when (ex is ArgumentException || ex is MethodAccessException || ex is TargetException)
            {
                throw new CanvasDirectorException(
                    "solve_failed",
                    $"CanvasDirector could not invoke Grasshopper solve: {ex.Message}",
                    503);
            }

            var afterToken = ReadSolutionToken(document);
            if (afterToken == null)
            {
                throw new CanvasDirectorException(
                    "solve_failed",
                    "CanvasDirector could not read the Grasshopper solution token after solving.",
                    503);
            }

            if (string.Equals(beforeToken, afterToken, StringComparison.Ordinal))
            {
                throw new CanvasDirectorException(
                    "solution_stale",
                    "CanvasDirector fresh solve did not advance the Grasshopper solution token.",
                    409);
            }
        }

        internal static void ValidateDocumentIdentity(object document, CanvasDirectorExtractRequest request)
        {
            if (string.IsNullOrWhiteSpace(request.DocumentId))
            {
                return;
            }

            foreach (var propertyName in new[] { "DocumentID", "RuntimeID", "FilePath" })
            {
                var actual = ReadStringProperty(document, propertyName);
                if (!string.IsNullOrWhiteSpace(actual) &&
                    string.Equals(actual, request.DocumentId, StringComparison.Ordinal))
                {
                    return;
                }
            }

            throw new CanvasDirectorException(
                "document_mismatch",
                "CanvasDirector request does not match the active Grasshopper document.",
                409);
        }

        internal static CanvasDirectorExtractionEnvelope ParseExportPayload(
            string payloadJson,
            CanvasDirectorExtractRequest? request = null)
        {
            JsonDocument document;
            try
            {
                document = JsonDocument.Parse(payloadJson);
            }
            catch (JsonException ex)
            {
                throw new CanvasDirectorException(
                    "export_schema_mismatch",
                    $"CanvasDirector export payload is not valid JSON: {ex.Message}",
                    400);
            }

            using (document)
            {
                var root = document.RootElement;
                if (root.ValueKind != JsonValueKind.Object)
                {
                    throw ExportSchemaMismatch("CanvasDirector export payload must be a JSON object.");
                }

                if (!TryGetString(root, "metadata_kind", out var metadataKind) ||
                    !string.Equals(metadataKind, ExportMetadataKind, StringComparison.Ordinal))
                {
                    throw ExportSchemaMismatch("CanvasDirector export payload missing declared metadata_kind marker.");
                }

                if (!TryGetString(root, "export_id", out var exportId) ||
                    !TryGetString(root, "template_id", out _) ||
                    !TryGetString(root, "template_version", out _) ||
                    !root.TryGetProperty("payload", out _))
                {
                    throw ExportSchemaMismatch("CanvasDirector export payload missing required fields.");
                }

                var requestedExportId = request?.ExportId;
                if (!string.IsNullOrWhiteSpace(requestedExportId) &&
                    !string.Equals(exportId, requestedExportId, StringComparison.Ordinal))
                {
                    throw DocumentMismatch("CanvasDirector export_id does not match the request.");
                }

                var requestedProposalId = request?.ProposalId;
                if (!string.IsNullOrWhiteSpace(requestedProposalId))
                {
                    if (!TryGetString(root, "proposal_id", out var proposalId) ||
                        !string.Equals(proposalId, requestedProposalId, StringComparison.Ordinal))
                    {
                        throw DocumentMismatch("CanvasDirector proposal_id does not match the request.");
                    }
                }

                return CanvasDirectorExtractionEnvelope.FromState(root.Clone());
            }
        }

        internal static object ResolveActiveGrasshopperDocument()
        {
            var instancesType = Type.GetType("Grasshopper.Instances, Grasshopper", throwOnError: false);
            var activeCanvas = instancesType
                ?.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static)
                ?.GetValue(null);
            var document = activeCanvas == null
                ? null
                : activeCanvas
                    .GetType()
                    .GetProperty("Document", BindingFlags.Public | BindingFlags.Instance)
                    ?.GetValue(activeCanvas);

            if (document == null)
            {
                throw new CanvasDirectorException(
                    "grasshopper_not_ready",
                    "CanvasDirector extraction requires an active Grasshopper document.",
                    503);
            }

            return document;
        }

        internal static string TryExtractFromDocument(object document, CanvasDirectorExtractRequest request)
        {
            var objects = document.GetType()
                .GetProperty("Objects", BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(document) as IEnumerable;

            if (objects == null)
            {
                throw new CanvasDirectorException(
                    "grasshopper_not_ready",
                    "CanvasDirector extraction requires Grasshopper document objects.",
                    503);
            }

            string? payload = null;
            var payloadCount = 0;

            foreach (var component in objects)
            {
                if (component == null)
                {
                    continue;
                }

                // TEMPORARY first-slice harness only: discovery uses a nickname marker until the
                // dedicated export component contract exists. Payload metadata remains authoritative.
                var nickName = ReadStringProperty(component, "NickName");
                if (nickName == null ||
                    !nickName.StartsWith(TemporaryExportNickNamePrefix, StringComparison.Ordinal))
                {
                    continue;
                }

                var exportId = nickName.Substring(TemporaryExportNickNamePrefix.Length);
                if (!string.IsNullOrWhiteSpace(request.ExportId) &&
                    !string.Equals(exportId, request.ExportId, StringComparison.Ordinal))
                {
                    continue;
                }

                var componentPayload = ReadFirstOutputString(component);
                if (componentPayload == null)
                {
                    continue;
                }

                payload = componentPayload;
                payloadCount++;
            }

            if (payloadCount == 0)
            {
                throw new CanvasDirectorException(
                    "export_not_found",
                    "CanvasDirector export marker was not found in the active Grasshopper document.",
                    404);
            }

            if (payloadCount > 1)
            {
                throw new CanvasDirectorException(
                    "multiple_exports_ambiguous",
                    "CanvasDirector found multiple matching export markers in the active Grasshopper document.",
                    409);
            }

            return payload!;
        }

        internal static string? ReadSolutionToken(object document)
        {
            var history = document.GetType()
                .GetProperty("SolutionHistory", BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(document);
            var historyCount = ReadEnumerableCount(history);
            var solutionSpan = document.GetType()
                .GetProperty("SolutionSpan", BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(document);

            if (historyCount != null || solutionSpan != null)
            {
                var historyToken = historyCount?.ToString(CultureInfo.InvariantCulture) ?? "unknown";
                var spanToken = ToInvariantString(solutionSpan) ?? "unknown";
                return historyToken + ":" + spanToken;
            }

            return ReadStringProperty(document, "SolutionToken")
                ?? ReadStringProperty(document, "SolutionSerial");
        }

        internal static int? ReadIntProperty(object target, string propertyName)
        {
            var value = target.GetType()
                .GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(target);
            if (value == null)
            {
                return null;
            }

            try
            {
                return Convert.ToInt32(value, CultureInfo.InvariantCulture);
            }
            catch (Exception ex) when (ex is FormatException || ex is InvalidCastException || ex is OverflowException)
            {
                return null;
            }
        }

        internal static string? ReadStringProperty(object target, string propertyName)
        {
            var value = target.GetType()
                .GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(target);
            return ToInvariantString(value);
        }

        private static string? ReadFirstOutputString(object component)
        {
            var parameters = component.GetType()
                .GetProperty("Params", BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(component);
            var outputs = parameters?.GetType()
                .GetProperty("Output", BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(parameters) as IEnumerable;
            var firstOutput = FirstOrDefault(outputs);
            var volatileData = firstOutput?.GetType()
                .GetProperty("VolatileData", BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(firstOutput);
            var allData = volatileData?.GetType()
                .GetMethod("AllData", BindingFlags.Public | BindingFlags.Instance)
                ?.Invoke(volatileData, Array.Empty<object>()) as IEnumerable;
            var firstGoo = FirstOrDefault(allData);
            var value = firstGoo?.GetType()
                .GetProperty("Value", BindingFlags.Public | BindingFlags.Instance)
                ?.GetValue(firstGoo);

            return ToInvariantString(value);
        }

        private static object? FirstOrDefault(IEnumerable? values)
        {
            if (values == null)
            {
                return null;
            }

            foreach (var value in values)
            {
                return value;
            }

            return null;
        }

        private static int? ReadEnumerableCount(object? value)
        {
            if (value is ICollection collection)
            {
                return collection.Count;
            }

            if (value is IEnumerable enumerable)
            {
                var count = 0;
                foreach (var _ in enumerable)
                {
                    count++;
                }

                return count;
            }

            return null;
        }

        private static string? ToInvariantString(object? value)
        {
            switch (value)
            {
                case null:
                    return null;
                case string text:
                    return text;
                case IFormattable formattable:
                    return formattable.ToString(null, CultureInfo.InvariantCulture);
                default:
                    return Convert.ToString(value, CultureInfo.InvariantCulture);
            }
        }

        private static bool TryGetString(JsonElement root, string name, out string? value)
        {
            if (root.TryGetProperty(name, out var element) &&
                element.ValueKind == JsonValueKind.String)
            {
                value = element.GetString();
                return true;
            }

            value = null;
            return false;
        }

        private static CanvasDirectorException ExportSchemaMismatch(string message)
        {
            return new CanvasDirectorException("export_schema_mismatch", message, 400);
        }

        private static CanvasDirectorException DocumentMismatch(string message)
        {
            return new CanvasDirectorException("document_mismatch", message, 409);
        }
    }
}
