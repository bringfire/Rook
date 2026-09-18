using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Reflection;

namespace Rook.InternalBridge
{
    /// <summary>
    /// Minimal managed GH core extracted from the HTTP handler as the first step
    /// toward an internal native-owned bridge.
    /// </summary>
    public interface IGrasshopperCore
    {
        BridgeResult<GrasshopperStatusDto> GetStatus();
        BridgeResult<GrasshopperDocumentInfoDto> GetDocumentInfo();
        BridgeResult<GrasshopperQueryDto> QueryDocument();
        BridgeResult<GrasshopperSelectionDto> GetSelection();
    }

    public sealed class GrasshopperCore : IGrasshopperCore
    {
        private Assembly? _ghAssembly;
        private readonly object _lock = new();

        public BridgeResult<GrasshopperStatusDto> GetStatus()
        {
            try
            {
                return BridgeResult<GrasshopperStatusDto>.Ok(ObserveStatus());
            }
            catch (Exception ex)
            {
                return BridgeResult<GrasshopperStatusDto>.Ok(new GrasshopperStatusDto
                {
                    Available = false,
                    HasActiveCanvas = false,
                    HasActiveDocument = false,
                    VisibilityUnknown = true,
                    ReadyForEdit = false,
                    Warnings = new[] { $"Grasshopper status inspection failed: {ex.Message}" },
                });
            }
        }

        private GrasshopperStatusDto ObserveStatus()
        {
            var dispatch = GrasshopperDispatchContext.Current;
            Assembly? assembly;
            object? canvas;
            object? document;
            if (dispatch is not null)
            {
                assembly = dispatch.Assembly;
                canvas = dispatch.Canvas;
                document = dispatch.Document;
            }
            else
            {
                lock (_lock)
                {
                    _ghAssembly ??= AppDomain.CurrentDomain.GetAssemblies()
                        .FirstOrDefault(a => a.GetName().Name == "Grasshopper");
                }

                assembly = _ghAssembly;
                canvas = null;
                document = null;
            }

            if (assembly == null)
            {
                return new GrasshopperStatusDto
                {
                    Available = false,
                    HasActiveCanvas = false,
                    HasActiveDocument = false,
                    VisibilityUnknown = true,
                    ReadyForEdit = false,
                    Warnings = new[] { "Grasshopper assembly is not loaded. Open Grasshopper before using GH canvas tools." },
                };
            }

            var warnings = new List<string>();
            var instancesType = assembly.GetType("Grasshopper.Instances");
            var available = instancesType != null;
            bool? canvasVisible = null;
            var visibilityUnknown = true;

            if (dispatch is not null)
            {
                canvasVisible = DetectCanvasVisible(canvas!, out visibilityUnknown);
                if (visibilityUnknown)
                    warnings.Add("Grasshopper canvas visibility could not be detected.");
            }
            else if (instancesType == null)
            {
                warnings.Add("Grasshopper.Instances type was not found in the loaded Grasshopper assembly.");
            }
            else
            {
                var canvasProp = instancesType.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static);
                canvas = canvasProp?.GetValue(null);
                if (canvas != null)
                {
                    var docProp = canvas.GetType().GetProperty("Document");
                    document = docProp?.GetValue(canvas);
                    canvasVisible = DetectCanvasVisible(canvas, out visibilityUnknown);
                    if (visibilityUnknown)
                        warnings.Add("Grasshopper canvas visibility could not be detected.");
                }
            }

            var objectCount = 0;
            try
            {
                if (document != null)
                {
                    var objectsProp = document.GetType().GetProperty("Objects");
                    var objects = objectsProp?.GetValue(document) as IEnumerable;
                    if (objects != null)
                        objectCount = objects.Cast<object>().Count();
                }
            }
            catch
            {
                // Keep status non-fatal if object enumeration fails.
            }

            var documentPath = GetStringProperty(document, "FilePath") ?? "";
            var documentName = GetStringProperty(document, "DisplayName");
            if (string.IsNullOrEmpty(documentName) && !string.IsNullOrEmpty(documentPath))
                documentName = System.IO.Path.GetFileName(documentPath);

            // Solver state for gh_status (report only — NEVER gates ReadyForEdit). See spec §7.
            var solver = document != null ? GhSolverState.Inspect(document) : default;

            return new GrasshopperStatusDto
            {
                Available = available,
                AssemblyVersion = assembly.GetName().Version?.ToString() ?? "",
                HasActiveCanvas = canvas != null,
                CanvasVisible = canvasVisible,
                VisibilityUnknown = visibilityUnknown,
                HasActiveDocument = document != null,
                DocumentId = GetObservedDocumentId(document, dispatch?.DocumentId),
                DocumentName = documentName,
                DocumentPath = documentPath,
                ReadyForEdit = available && canvas != null && document != null && canvasVisible != false,
                ObjectCount = objectCount,
                Warnings = warnings,
                SolverEnabled = solver.Enabled,
                SolverStateKnown = solver.Known,
                SolverGlobalEnableSolutions = solver.GlobalEnableSolutions,
                SolverDocumentEnabled = solver.DocumentEnabled,
                SolutionState = solver.SolutionState,
            };
        }

        public BridgeResult<GrasshopperDocumentInfoDto> GetDocumentInfo()
        {
            var status = ObserveStatus();
            if (!status.HasActiveDocument || !status.HasActiveCanvas || status.CanvasVisible == false)
                return BridgeResult<GrasshopperDocumentInfoDto>.Fail(BuildNotReadyMessage(status));

            var gh = ResolveContext();
            if (!gh.Success)
                return BridgeResult<GrasshopperDocumentInfoDto>.Fail(gh.Error ?? "Grasshopper unavailable");

            try
            {
                string? filePath = null;
                var filePathProp = gh.Document!.GetType().GetProperty("FilePath");
                if (filePathProp != null)
                    filePath = filePathProp.GetValue(gh.Document)?.ToString();

                string? displayName = null;
                var displayNameProp = gh.Document.GetType().GetProperty("DisplayName");
                if (displayNameProp != null)
                    displayName = displayNameProp.GetValue(gh.Document)?.ToString();

                var name = "untitled.gh";
                if (!string.IsNullOrEmpty(filePath))
                    name = System.IO.Path.GetFileName(filePath);
                else if (!string.IsNullOrEmpty(displayName))
                    name = displayName;

                return BridgeResult<GrasshopperDocumentInfoDto>.Ok(new GrasshopperDocumentInfoDto
                {
                    Name = name,
                    Path = filePath ?? "",
                    DisplayName = displayName ?? "Untitled",
                    IsSaved = !string.IsNullOrEmpty(filePath),
                });
            }
            catch (Exception ex)
            {
                return BridgeResult<GrasshopperDocumentInfoDto>.Fail($"GetDocumentInfo failed: {ex.Message}");
            }
        }

        public BridgeResult<GrasshopperQueryDto> QueryDocument()
        {
            var status = ObserveStatus();
            if (!status.ReadyForEdit)
                return BridgeResult<GrasshopperQueryDto>.Fail(BuildNotReadyMessage(status));

            var gh = ResolveContext();
            if (!gh.Success)
                return BridgeResult<GrasshopperQueryDto>.Fail(gh.Error ?? "Grasshopper unavailable");

            try
            {
                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = objectsProp?.GetValue(gh.Document) as IEnumerable;

                var objectList = new List<GrasshopperCanvasObjectDto>();
                if (objects != null)
                {
                    foreach (var obj in objects)
                    {
                        objectList.Add(ProjectCanvasObject(obj));
                    }
                }

                return BridgeResult<GrasshopperQueryDto>.Ok(new GrasshopperQueryDto
                {
                    ObjectCount = objectList.Count,
                    Objects = objectList,
                });
            }
            catch (Exception ex)
            {
                return BridgeResult<GrasshopperQueryDto>.Fail($"QueryDocument failed: {ex.Message}");
            }
        }

        public BridgeResult<GrasshopperSelectionDto> GetSelection()
        {
            var gh = ResolveContext();
            if (!gh.Success)
                return BridgeResult<GrasshopperSelectionDto>.Fail(gh.Error ?? "Grasshopper unavailable");

            try
            {
                var selectedMethod = gh.Document!.GetType().GetMethod("SelectedObjects", Type.EmptyTypes);
                var selectedObjects = selectedMethod?.Invoke(gh.Document, null) as IEnumerable;

                var objectList = new List<GrasshopperCanvasObjectDto>();
                if (selectedObjects != null)
                {
                    foreach (var obj in selectedObjects)
                    {
                        objectList.Add(ProjectCanvasObject(obj));
                    }
                }

                return BridgeResult<GrasshopperSelectionDto>.Ok(new GrasshopperSelectionDto
                {
                    Count = objectList.Count,
                    Objects = objectList,
                });
            }
            catch (Exception ex)
            {
                return BridgeResult<GrasshopperSelectionDto>.Fail($"GetSelection failed: {ex.Message}");
            }
        }

        private ResolvedGrasshopperContext ResolveContext()
        {
            var dispatch = GrasshopperDispatchContext.Current;
            if (dispatch is not null)
            {
                return ResolvedGrasshopperContext.Ok(
                    dispatch.Assembly!,
                    dispatch.Canvas!,
                    dispatch.Document!);
            }

            lock (_lock)
            {
                _ghAssembly ??= AppDomain.CurrentDomain.GetAssemblies()
                    .FirstOrDefault(a => a.GetName().Name == "Grasshopper");
            }

            if (_ghAssembly == null)
            {
                return ResolvedGrasshopperContext.Fail("Grasshopper assembly not found. Is Grasshopper open?");
            }

            var instancesType = _ghAssembly.GetType("Grasshopper.Instances");
            if (instancesType == null)
            {
                return ResolvedGrasshopperContext.Fail("Grasshopper.Instances type not found", _ghAssembly);
            }

            var canvasProp = instancesType.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static);
            var canvas = canvasProp?.GetValue(null);
            if (canvas == null)
            {
                return ResolvedGrasshopperContext.Fail("No active Grasshopper canvas", _ghAssembly);
            }

            var docProp = canvas.GetType().GetProperty("Document");
            var document = docProp?.GetValue(canvas);
            if (document == null)
            {
                return ResolvedGrasshopperContext.Fail(
                    "No active Grasshopper document",
                    _ghAssembly,
                    canvas);
            }

            return ResolvedGrasshopperContext.Ok(_ghAssembly, canvas, document);
        }

        private static string? GetObservedDocumentId(object? document, Guid? capturedDocumentId)
        {
            if (capturedDocumentId.HasValue)
            {
                return capturedDocumentId.Value.ToString("D");
            }

            return GetStringProperty(document, "DocumentID")
                ?? GetStringProperty(document, "DocumentGuid")
                ?? GetStringProperty(document, "InstanceGuid")
                ?? GetStringProperty(document, "Guid");
        }

        private static string BuildNotReadyMessage(GrasshopperStatusDto status)
        {
            if (!status.Available)
                return "Grasshopper is not available. Open Grasshopper before using GH canvas tools.";
            if (!status.HasActiveCanvas)
                return "No active Grasshopper canvas. Open the Grasshopper editor before using GH canvas tools.";
            if (!status.HasActiveDocument)
                return "No active Grasshopper document. Open or create a Grasshopper document before using GH canvas tools.";
            if (status.CanvasVisible == false)
                return "Grasshopper canvas is not visible. Show the Grasshopper editor before using GH canvas tools.";
            return "Grasshopper is not ready for canvas tools.";
        }

        private static bool? DetectCanvasVisible(object canvas, out bool visibilityUnknown)
        {
            visibilityUnknown = true;
            bool? visible = TryGetBooleanProperty(canvas, "Visible")
                ?? TryGetBooleanProperty(canvas, "IsVisible");

            var findForm = canvas.GetType().GetMethod("FindForm", Type.EmptyTypes);
            var form = findForm?.Invoke(canvas, null);
            var formVisible = form != null
                ? TryGetBooleanProperty(form, "Visible") ?? TryGetBooleanProperty(form, "IsVisible")
                : null;

            if (visible == false || formVisible == false)
            {
                visibilityUnknown = false;
                return false;
            }

            if (visible.HasValue || formVisible.HasValue)
            {
                visibilityUnknown = false;
                return (visible ?? true) && (formVisible ?? true);
            }

            return null;
        }

        private static bool? TryGetBooleanProperty(object obj, string propertyName)
        {
            try
            {
                var prop = obj.GetType().GetProperty(propertyName);
                var value = prop?.GetValue(obj);
                return value is bool flag ? flag : null;
            }
            catch
            {
                return null;
            }
        }

        private static string? GetStringProperty(object? obj, string propertyName)
        {
            if (obj == null)
                return null;
            try
            {
                return obj.GetType().GetProperty(propertyName)?.GetValue(obj)?.ToString();
            }
            catch
            {
                return null;
            }
        }

        private static GrasshopperCanvasObjectDto ProjectCanvasObject(object obj)
        {
            var dto = new GrasshopperCanvasObjectDto
            {
                Type = obj.GetType().Name,
                Name = obj.GetType().GetProperty("Name")?.GetValue(obj)?.ToString(),
                NickName = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString(),
                Guid = obj.GetType().GetProperty("InstanceGuid")?.GetValue(obj)?.ToString(),
                Category = obj.GetType().GetProperty("Category")?.GetValue(obj)?.ToString(),
                SubCategory = obj.GetType().GetProperty("SubCategory")?.GetValue(obj)?.ToString(),
            };

            var attrProp = obj.GetType().GetProperty("Attributes");
            var attr = attrProp?.GetValue(obj);
            if (attr == null)
                return dto;

            var pivotProp = attr.GetType().GetProperty("Pivot");
            if (pivotProp?.GetValue(attr) is PointF pivot)
            {
                dto.Position = new GrasshopperPointDto { X = pivot.X, Y = pivot.Y };
            }

            var boundsProp = attr.GetType().GetProperty("Bounds");
            if (boundsProp?.GetValue(attr) is RectangleF bounds)
            {
                dto.Size = new GrasshopperSizeDto { Width = bounds.Width, Height = bounds.Height };
            }

            return dto;
        }

        private sealed class ResolvedGrasshopperContext
        {
            private ResolvedGrasshopperContext(bool success, string? error, Assembly? assembly, object? canvas, object? document)
            {
                Success = success;
                Error = error;
                Assembly = assembly;
                Canvas = canvas;
                Document = document;
            }

            public bool Success { get; }
            public string? Error { get; }
            public Assembly? Assembly { get; }
            public object? Canvas { get; }
            public object? Document { get; }

            public static ResolvedGrasshopperContext Ok(Assembly assembly, object canvas, object document)
            {
                return new ResolvedGrasshopperContext(true, null, assembly, canvas, document);
            }

            public static ResolvedGrasshopperContext Fail(string error, Assembly? assembly = null, object? canvas = null)
            {
                return new ResolvedGrasshopperContext(false, error, assembly, canvas, null);
            }
        }
    }

    public sealed class BridgeResult<T>
    {
        public bool Success { get; set; }
        public T? Data { get; set; }
        public string? Error { get; set; }

        public static BridgeResult<T> Ok(T data)
        {
            return new BridgeResult<T> { Success = true, Data = data };
        }

        public static BridgeResult<T> Fail(string error)
        {
            return new BridgeResult<T> { Success = false, Error = error };
        }
    }

    public sealed class GrasshopperStatusDto
    {
        public bool Available { get; set; }
        public string AssemblyVersion { get; set; } = "";
        public bool HasActiveCanvas { get; set; }
        public bool? CanvasVisible { get; set; }
        public bool VisibilityUnknown { get; set; }
        public bool HasActiveDocument { get; set; }
        public string? DocumentId { get; set; }
        public string? DocumentName { get; set; }
        public string? DocumentPath { get; set; }
        public bool ReadyForEdit { get; set; }
        public int ObjectCount { get; set; }
        public IReadOnlyList<string> Warnings { get; set; } = Array.Empty<string>();
        public bool? SolverEnabled { get; set; }
        public bool SolverStateKnown { get; set; }
        public bool? SolverGlobalEnableSolutions { get; set; }
        public bool? SolverDocumentEnabled { get; set; }
        public string? SolutionState { get; set; }
        public bool RirRepairAttempted { get; set; }
        public bool RirRepairHeld { get; set; }
        public string? RirRepairReason { get; set; }
        public string? RirRepairSource { get; set; }
    }

    public sealed class GrasshopperDocumentInfoDto
    {
        public string Name { get; set; } = "";
        public string Path { get; set; } = "";
        public string DisplayName { get; set; } = "";
        public bool IsSaved { get; set; }
    }

    public sealed class GrasshopperQueryDto
    {
        public int ObjectCount { get; set; }
        public IReadOnlyList<GrasshopperCanvasObjectDto> Objects { get; set; } = Array.Empty<GrasshopperCanvasObjectDto>();
    }

    public sealed class GrasshopperSelectionDto
    {
        public int Count { get; set; }
        public IReadOnlyList<GrasshopperCanvasObjectDto> Objects { get; set; } = Array.Empty<GrasshopperCanvasObjectDto>();
    }

    public sealed class GrasshopperCanvasObjectDto
    {
        public string Type { get; set; } = "";
        public string? Name { get; set; }
        public string? NickName { get; set; }
        public string? Guid { get; set; }
        public string? Category { get; set; }
        public string? SubCategory { get; set; }
        public GrasshopperPointDto? Position { get; set; }
        public GrasshopperSizeDto? Size { get; set; }
    }

    public sealed class GrasshopperPointDto
    {
        public float X { get; set; }
        public float Y { get; set; }
    }

    public sealed class GrasshopperSizeDto
    {
        public float Width { get; set; }
        public float Height { get; set; }
    }
}
