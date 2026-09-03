using System;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;

namespace Rook.InternalBridge
{
    internal enum GhManagedDispatchScope
    {
        DocumentIndependent,
        Observation,
        Mutation,
        Transition,
    }

    internal interface IGrasshopperDispatchSource
    {
        GrasshopperDispatchCapture Capture();
    }

    internal sealed class GrasshopperDispatchCapture
    {
        private GrasshopperDispatchCapture(
            bool available,
            string? error,
            Assembly? assembly,
            object? canvas,
            object? document,
            Guid? documentId)
        {
            IsAvailable = available;
            Error = error;
            Assembly = assembly;
            Canvas = canvas;
            Document = document;
            DocumentId = documentId;
        }

        internal bool IsAvailable { get; }
        internal string? Error { get; }
        internal Assembly? Assembly { get; }
        internal object? Canvas { get; }
        internal object? Document { get; }
        internal Guid? DocumentId { get; }

        internal static GrasshopperDispatchCapture Available(
            Assembly assembly,
            object canvas,
            object document)
        {
            var documentIdProperty = document.GetType().GetProperty(
                "DocumentID",
                BindingFlags.Instance | BindingFlags.Public);
            if (documentIdProperty?.PropertyType != typeof(Guid) ||
                documentIdProperty.GetValue(document) is not Guid documentId ||
                documentId == Guid.Empty)
            {
                return Unavailable("The active Grasshopper document has no valid DocumentID.");
            }

            return new GrasshopperDispatchCapture(
                true,
                null,
                assembly,
                canvas,
                document,
                documentId);
        }

        internal static GrasshopperDispatchCapture Unavailable(string error) =>
            new(false, error, null, null, null, null);
    }

    internal sealed class GrasshopperDispatchFrame
    {
        internal GrasshopperDispatchFrame(GrasshopperDispatchCapture capture)
        {
            Assembly = capture.Assembly;
            Canvas = capture.Canvas;
            Document = capture.Document;
            DocumentId = capture.DocumentId!.Value;
        }

        internal Assembly? Assembly { get; }
        internal object? Canvas { get; }
        internal object? Document { get; }
        internal Guid DocumentId { get; }
    }

    internal static class GrasshopperDispatchContext
    {
        private static readonly AsyncLocal<GrasshopperDispatchFrame?> CurrentFrame = new();
        private static readonly JsonSerializerOptions ProjectionJsonOptions = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        };

        internal static GrasshopperDispatchFrame? Current => CurrentFrame.Value;

        internal static IGrasshopperDispatchSource ProductionSource { get; } =
            new ReflectionGrasshopperDispatchSource();

        internal static ApiResponse Execute(
            IGrasshopperDispatchSource source,
            GhManagedDispatchScope scope,
            string? expectedDocumentId,
            Func<ApiResponse> operation)
        {
            if (scope == GhManagedDispatchScope.DocumentIndependent)
            {
                return operation();
            }

            Guid? expected = null;
            if (scope == GhManagedDispatchScope.Mutation)
            {
                if (expectedDocumentId is null)
                {
                    return Failure("gh_target_required", "A Grasshopper document identity is required.");
                }

                if (!Guid.TryParseExact(expectedDocumentId, "D", out var parsed) ||
                    parsed == Guid.Empty ||
                    !string.Equals(expectedDocumentId, parsed.ToString("D"), StringComparison.Ordinal))
                {
                    return Failure("invalid_arguments", "expectedGhDocumentId must be a canonical lowercase UUID.");
                }

                expected = parsed;
            }
            else if (scope == GhManagedDispatchScope.Observation && expectedDocumentId is not null)
            {
                if (!Guid.TryParseExact(expectedDocumentId, "D", out var parsed) ||
                    parsed == Guid.Empty ||
                    !string.Equals(expectedDocumentId, parsed.ToString("D"), StringComparison.Ordinal))
                {
                    return Failure("invalid_arguments", "expectedGhDocumentId must be a canonical lowercase UUID.");
                }

                expected = parsed;
            }

            if (scope == GhManagedDispatchScope.Transition)
            {
                var transitionResult = operation();
                if (!transitionResult.Success)
                {
                    return transitionResult;
                }

                var resultingCapture = source.Capture();
                return resultingCapture.IsAvailable
                    ? WithDocumentId(transitionResult, resultingCapture.DocumentId!.Value)
                    : Failure("gh_target_unavailable", resultingCapture.Error ?? "No active Grasshopper document.");
            }

            var capture = source.Capture();
            if (!capture.IsAvailable)
            {
                return Failure("gh_target_unavailable", capture.Error ?? "No active Grasshopper document.");
            }

            if (expected.HasValue && capture.DocumentId != expected)
            {
                return Failure("gh_target_changed", "The active Grasshopper document changed before dispatch.");
            }

            return ExecuteCaptured(capture, operation);
        }

        internal static ApiResponse ExecuteCaptured(
            GrasshopperDispatchCapture capture,
            Func<ApiResponse> operation)
        {
            if (!capture.IsAvailable)
            {
                return Failure("gh_target_unavailable", capture.Error ?? "No active Grasshopper document.");
            }

            var previous = CurrentFrame.Value;
            try
            {
                CurrentFrame.Value = new GrasshopperDispatchFrame(capture);
                var result = operation();
                return result.Success
                    ? WithDocumentId(result, capture.DocumentId!.Value)
                    : result;
            }
            finally
            {
                CurrentFrame.Value = previous;
            }
        }

        private static ApiResponse Failure(string error, string message) => new()
        {
            Success = false,
            Data = new { error, message },
        };

        private static ApiResponse WithDocumentId(ApiResponse response, Guid documentId)
        {
            JsonObject data;
            if (response.Data is null)
            {
                data = new JsonObject();
            }
            else
            {
                data = JsonSerializer.SerializeToNode(response.Data, ProjectionJsonOptions) as JsonObject
                    ?? new JsonObject
                    {
                        ["value"] = JsonSerializer.SerializeToNode(
                            response.Data,
                            ProjectionJsonOptions),
                    };
            }

            data["ghDocumentId"] = documentId.ToString("D");
            response.Data = data;
            return response;
        }

        private sealed class ReflectionGrasshopperDispatchSource : IGrasshopperDispatchSource
        {
            public GrasshopperDispatchCapture Capture()
            {
                var assembly = Array.Find(
                    AppDomain.CurrentDomain.GetAssemblies(),
                    candidate => candidate.GetName().Name == "Grasshopper");
                if (assembly is null)
                {
                    return GrasshopperDispatchCapture.Unavailable("Grasshopper assembly is not loaded.");
                }

                var instances = assembly.GetType("Grasshopper.Instances");
                var canvas = instances?
                    .GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static)?
                    .GetValue(null);
                if (canvas is null)
                {
                    return GrasshopperDispatchCapture.Unavailable("No active Grasshopper canvas.");
                }

                var document = canvas.GetType()
                    .GetProperty("Document", BindingFlags.Public | BindingFlags.Instance)?
                    .GetValue(canvas);
                return document is null
                    ? GrasshopperDispatchCapture.Unavailable("No active Grasshopper document.")
                    : GrasshopperDispatchCapture.Available(assembly, canvas, document);
            }
        }
    }
}
