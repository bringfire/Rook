using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Rook.InternalBridge;

namespace Rook.Handlers
{
    internal readonly struct GhOpenDocumentPreflightResult
    {
        public bool Success { get; init; }
        public string? Path { get; init; }
        public string? ErrorCode { get; init; }
    }

    /// <summary>
    /// Handler for direct Grasshopper canvas manipulation via reflection.
    /// Provides MCP tools for creating and managing GH components without external dependencies.
    /// </summary>
    public partial class GrasshopperHandler
    {
        private readonly IGrasshopperCore _bridgeCore;
        private readonly Func<bool> _runningAsRhinoInside;
        private Assembly? _ghAssembly;
        private readonly object _lock = new();
        private readonly ShortIdRegistry _idRegistry = new();
        private static readonly Regex GhEditTempIdRegex = new(
            @"\AT[A-Za-z0-9_]{1,63}\z",
            RegexOptions.CultureInvariant);
        private static readonly Regex GhEditComponentIdRegex = new(
            @"\AC[1-9][0-9]*\z",
            RegexOptions.CultureInvariant);

        public GrasshopperHandler()
            : this(null, () => Rhino.Runtime.HostUtils.RunningAsRhinoInside, null, null, null)
        {
        }

        internal GrasshopperHandler(
            IGrasshopperCore? bridgeCore = null,
            Func<bool>? runningAsRhinoInside = null,
            GhSolveReceiptRegistry? solveReceiptRegistry = null,
            GhSolutionLifecycleAdapter? solutionLifecycleAdapter = null,
            GhCanvasDocumentLifecycleAdapter? canvasDocumentLifecycleAdapter = null)
        {
            _bridgeCore = bridgeCore ?? new GrasshopperCore();
            _runningAsRhinoInside = runningAsRhinoInside ?? (() => Rhino.Runtime.HostUtils.RunningAsRhinoInside);
            _solveReceiptRegistry = solveReceiptRegistry ?? new GhSolveReceiptRegistry();
            _solutionLifecycleAdapter = solutionLifecycleAdapter ?? new GhSolutionLifecycleAdapter();
            _canvasDocumentLifecycleAdapter = canvasDocumentLifecycleAdapter ?? new GhCanvasDocumentLifecycleAdapter();
        }

        #region Core API

        /// <summary>
        /// GET /gh/status - Check if Grasshopper is available and get canvas info
        /// </summary>
        public ApiResponse GetStatus()
        {
            var status = _bridgeCore.GetStatus();
            if (status.Success && status.Data != null)
            {
                status.Data.RirRepairAttempted = false;
                status.Data.RirRepairHeld = false;
                status.Data.RirRepairReason = null;
                status.Data.RirRepairSource = null;
            }

            return ToApiResponse(status);
        }

        /// <summary>
        /// GET /gh/document - Get information about the active GH document
        /// </summary>
        public ApiResponse GetDocumentInfo()
        {
            var statusResult = _bridgeCore.GetStatus();
            var status = statusResult.Data;
            if (!statusResult.Success || status?.HasActiveDocument != true || status.HasActiveCanvas != true || status.CanvasVisible == false)
                return GrasshopperNotReadyResponse("gh_document", status, statusResult.Error);

            return ToApiResponse(_bridgeCore.GetDocumentInfo());
        }

        /// <summary>
        /// GET /gh/query - Query the current Grasshopper document state
        /// </summary>
        internal ApiResponse QueryDocument()
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_query");
            if (notReady != null)
                return notReady;

            return ToApiResponse(_bridgeCore.QueryDocument());
        }

        /// <summary>
        /// GET /gh/selection - Get currently selected objects on the canvas
        /// </summary>
        public ApiResponse GetSelection()
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_selection");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_selection", null, gh.Error);

            return ToApiResponse(_bridgeCore.GetSelection());
        }

        private static ApiResponse ToApiResponse<T>(BridgeResult<T> result)
        {
            return new ApiResponse
            {
                Success = result.Success,
                Data = result.Success ? result.Data : result.Error
            };
        }

        private ApiResponse? EnsureGrasshopperReadyForEdit(string operation)
        {
            var statusResult = _bridgeCore.GetStatus();
            var status = statusResult.Data;
            if (statusResult.Success && status?.ReadyForEdit == true)
                return null;

            return GrasshopperNotReadyResponse(operation, status, statusResult.Error);
        }

        private static ApiResponse GrasshopperNotReadyResponse(
            string operation,
            GrasshopperStatusDto? status,
            string? fallbackReason = null)
        {
            var reason = BuildGrasshopperNotReadyReason(status, fallbackReason);
            return new ApiResponse
            {
                Success = false,
                Data = new
                {
                    error = "grasshopper_not_ready",
                    errors = new[] { reason },
                    message = reason,
                    operation,
                    ready_for_edit = false,
                    verification_note = "Call gh_status to inspect readiness. Use an explicit lifecycle tool only if Grasshopper is the intended substrate.",
                    verified = false,
                    status,
                }
            };
        }

        private static string BuildGrasshopperNotReadyReason(
            GrasshopperStatusDto? status,
            string? fallbackReason = null)
        {
            if (status == null)
                return fallbackReason ?? "Grasshopper readiness could not be inspected.";
            if (!status.Available)
                return "Grasshopper is not available. Open Grasshopper before using GH canvas tools.";
            if (!status.HasActiveCanvas)
                return "No active Grasshopper canvas. Open the Grasshopper editor before using GH canvas tools.";
            if (!status.HasActiveDocument)
                return "No active Grasshopper document. Open or create a Grasshopper document before using GH canvas tools.";
            if (status.CanvasVisible == false)
                return "Grasshopper canvas is not visible. Show the Grasshopper editor before using GH canvas tools.";
            return fallbackReason ?? "Grasshopper is not ready for GH canvas tools.";
        }

        /// <summary>
        /// POST /gh/create-slider - Create a number slider on the canvas
        /// Body: { nickname?: string, min?: number, max?: number, value?: number, x?: number, y?: number }
        /// </summary>
        internal ApiResponse CreateSlider(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_create_slider");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_create_slider", null, gh.Error);

            // Parse parameters
            string nickname = "Slider";
            decimal min = 0, max = 100, value = 50;
            float x = 100, y = 100;

            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    if (args != null)
                    {
                        if (args.TryGetValue("nickname", out var nn)) nickname = nn.GetString() ?? nickname;
                        if (args.TryGetValue("min", out var minEl)) min = minEl.GetDecimal();
                        if (args.TryGetValue("max", out var maxEl)) max = maxEl.GetDecimal();
                        if (args.TryGetValue("value", out var valEl)) value = valEl.GetDecimal();
                        if (args.TryGetValue("x", out var xEl)) x = xEl.GetSingle();
                        if (args.TryGetValue("y", out var yEl)) y = yEl.GetSingle();
                    }
                }
                catch { /* Use defaults */ }
            }

            try
            {
                // Create GH_NumberSlider
                var sliderType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_NumberSlider");
                if (sliderType == null)
                    return new ApiResponse { Success = false, Data = "GH_NumberSlider type not found" };

                var slider = Activator.CreateInstance(sliderType);
                if (slider == null)
                    return new ApiResponse { Success = false, Data = "Failed to create slider instance" };

                // Set nickname
                var nicknameProp = sliderType.GetProperty("NickName");
                nicknameProp?.SetValue(slider, nickname);

                // Set slider range
                var sliderProp = sliderType.GetProperty("Slider");
                if (sliderProp != null)
                {
                    var sliderObj = sliderProp.GetValue(slider);
                    if (sliderObj != null)
                    {
                        var sliderObjType = sliderObj.GetType();
                        sliderObjType.GetProperty("Minimum")?.SetValue(sliderObj, min);
                        sliderObjType.GetProperty("Maximum")?.SetValue(sliderObj, max);
                        sliderObjType.GetProperty("Value")?.SetValue(sliderObj, value);
                    }
                }

                // Create attributes and set position
                var createAttrMethod = sliderType.GetMethod("CreateAttributes", BindingFlags.Public | BindingFlags.Instance);
                createAttrMethod?.Invoke(slider, null);

                var attrProp = sliderType.GetProperty("Attributes");
                if (attrProp != null)
                {
                    var attr = attrProp.GetValue(slider);
                    var pivotProp = attr?.GetType().GetProperty("Pivot");
                    pivotProp?.SetValue(attr, new PointF(x, y));
                }

                // Add to document
                var guid = AddObjectToDocument(gh.Document!, slider);

                // Record undo for slider creation
                try
                {
                    var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                    if (undoUtil != null)
                        RecordUndoEvent(undoUtil, "Rook: create slider", new List<object> { slider }, isAdd: true);
                }
                catch { /* undo recording is best-effort */ }

                // Refresh canvas
                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Created = true,
                        Type = "GH_NumberSlider",
                        NickName = nickname,
                        Guid = guid,
                        Range = new { Min = min, Max = max, Value = value },
                        Position = new { X = x, Y = y }
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"CreateSlider failed: {ex.InnerException?.Message ?? ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/create-panel - Create a text panel on the canvas
        /// Body: { content?: string, x?: number, y?: number }
        /// </summary>
        internal ApiResponse CreatePanel(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_create_panel");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_create_panel", null, gh.Error);

            string content = "Panel";
            float x = 100, y = 100;

            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    if (args != null)
                    {
                        if (args.TryGetValue("content", out var c)) content = c.GetString() ?? content;
                        if (args.TryGetValue("x", out var xEl)) x = xEl.GetSingle();
                        if (args.TryGetValue("y", out var yEl)) y = yEl.GetSingle();
                    }
                }
                catch { }
            }

            try
            {
                var panelType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Panel");
                if (panelType == null)
                    return new ApiResponse { Success = false, Data = "GH_Panel type not found" };

                var panel = Activator.CreateInstance(panelType);
                if (panel == null)
                    return new ApiResponse { Success = false, Data = "Failed to create panel instance" };

                // Set content via UserText property
                var userTextProp = panelType.GetProperty("UserText");
                userTextProp?.SetValue(panel, content);

                // Create attributes and set position
                var createAttrMethod = panelType.GetMethod("CreateAttributes", BindingFlags.Public | BindingFlags.Instance);
                createAttrMethod?.Invoke(panel, null);

                var attrProp = panelType.GetProperty("Attributes");
                if (attrProp != null)
                {
                    var attr = attrProp.GetValue(panel);
                    var pivotProp = attr?.GetType().GetProperty("Pivot");
                    pivotProp?.SetValue(attr, new PointF(x, y));
                }

                var guid = AddObjectToDocument(gh.Document!, panel);

                // Record undo for panel creation
                try
                {
                    var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                    if (undoUtil != null)
                        RecordUndoEvent(undoUtil, "Rook: create panel", new List<object> { panel }, isAdd: true);
                }
                catch { /* undo recording is best-effort */ }

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Created = true,
                        Type = "GH_Panel",
                        Content = content,
                        Guid = guid,
                        Position = new { X = x, Y = y }
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"CreatePanel failed: {ex.InnerException?.Message ?? ex.Message}"
                };
            }
        }

        /// <summary>
        /// GET /gh/value?guid=... - Get the current value of a slider, panel, or other input
        /// </summary>
        internal ApiResponse GetValue(string? guid)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_get_value");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_get_value", null, gh.Error);

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var obj = FindObjectById(gh.Document!, guid);
                if (obj == null)
                    return new ApiResponse { Success = false, Data = $"Object not found: {guid}" };

                var typeName = obj.GetType().Name;

                // Handle Number Slider
                if (typeName == "GH_NumberSlider")
                {
                    var sliderProp = obj.GetType().GetProperty("Slider");
                    var slider = sliderProp?.GetValue(obj);
                    if (slider != null)
                    {
                        var value = slider.GetType().GetProperty("Value")?.GetValue(slider);
                        var min = slider.GetType().GetProperty("Minimum")?.GetValue(slider);
                        var max = slider.GetType().GetProperty("Maximum")?.GetValue(slider);

                        return new ApiResponse
                        {
                            Success = true,
                            Data = new
                            {
                                Guid = guid,
                                Type = "slider",
                                Value = value,
                                Min = min,
                                Max = max
                            }
                        };
                    }
                }

                // Handle Panel
                if (typeName == "GH_Panel")
                {
                    var userTextProp = obj.GetType().GetProperty("UserText");
                    var content = userTextProp?.GetValue(obj)?.ToString() ?? "";

                    return new ApiResponse
                    {
                        Success = true,
                        Data = new
                        {
                            Guid = guid,
                            Type = "panel",
                            Value = content
                        }
                    };
                }

                // Handle Boolean Toggle
                if (typeName == "GH_BooleanToggle")
                {
                    var valueProp = obj.GetType().GetProperty("Value");
                    var value = valueProp?.GetValue(obj);

                    return new ApiResponse
                    {
                        Success = true,
                        Data = new
                        {
                            Guid = guid,
                            Type = "toggle",
                            Value = value
                        }
                    };
                }

                // Handle Value List
                if (typeName == "GH_ValueList")
                {
                    var selectedProp = obj.GetType().GetProperty("FirstSelectedItem");
                    var selected = selectedProp?.GetValue(obj);
                    string? selectedName = null;
                    object? selectedValue = null;

                    if (selected != null)
                    {
                        selectedName = selected.GetType().GetProperty("Name")?.GetValue(selected)?.ToString();
                        selectedValue = selected.GetType().GetProperty("Value")?.GetValue(selected)?.ToString();
                    }

                    return new ApiResponse
                    {
                        Success = true,
                        Data = new
                        {
                            Guid = guid,
                            Type = "valuelist",
                            SelectedName = selectedName,
                            SelectedValue = selectedValue
                        }
                    };
                }

                return new ApiResponse
                {
                    Success = false,
                    Data = $"Unsupported object type for value get: {typeName}"
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"GetValue failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/value - Set the value of a slider, panel, or toggle
        /// Body: { guid: string, value: number|string|bool }
        /// </summary>
        internal ApiResponse SetValue(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_set_value");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_set_value", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            string? guid = null;
            JsonElement valueEl = default;
            decimal? minValue = null;
            decimal? maxValue = null;
            string? readinessReceiptId = null;
            bool? solveRelevantMutationCommitted = false;
            object? mutationTarget = null;
            GhScheduleResult? scheduleResult = null;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args != null)
                {
                    if (args.TryGetValue("guid", out var g)) guid = g.GetString();
                    if (args.TryGetValue("value", out var v)) valueEl = v;
                    if (args.TryGetValue("min", out var minEl)) minValue = minEl.GetDecimal();
                    if (args.TryGetValue("max", out var maxEl)) maxValue = maxEl.GetDecimal();
                }
            }
            catch
            {
                return new ApiResponse { Success = false, Data = "Invalid body format" };
            }

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var obj = FindObjectById(gh.Document!, guid);
                if (obj == null)
                    return new ApiResponse { Success = false, Data = $"Object not found: {guid}" };

                var typeName = obj.GetType().Name;

                // Handle Number Slider
                if (typeName == "GH_NumberSlider")
                {
                    var sliderProp = obj.GetType().GetProperty("Slider");
                    var slider = sliderProp?.GetValue(obj);
                    if (slider != null)
                    {
                        var sliderType = slider.GetType();
                        decimal newValue = valueEl.GetDecimal();
                        var issue = BeginSetValueReceipt(gh.Document!, gh.Canvas!);
                        if (!issue.Issued)
                            return ReadinessIssueFailure(issue.Error!);
                        readinessReceiptId = issue.Receipt!.ReceiptId;
                        mutationTarget = obj;

                        // Record generic undo after reservation and before changing the slider.
                        try
                        {
                            var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                            if (undoUtil != null)
                                RecordGenericObjectUndoEvent(undoUtil, "Rook: set value", obj);
                        }
                        catch { /* undo recording is best-effort */ }

                        // Set min/max first if provided (must be set before value)
                        if (minValue.HasValue)
                        {
                            var minimumProperty = sliderType.GetProperty("Minimum")
                                ?? throw new InvalidOperationException("Slider minimum property unavailable");
                            try
                            {
                                minimumProperty.SetValue(slider, minValue.Value);
                                solveRelevantMutationCommitted = true;
                            }
                            catch
                            {
                                if (solveRelevantMutationCommitted != true)
                                    solveRelevantMutationCommitted = null;
                                throw;
                            }
                        }
                        if (maxValue.HasValue)
                        {
                            var maximumProperty = sliderType.GetProperty("Maximum")
                                ?? throw new InvalidOperationException("Slider maximum property unavailable");
                            try
                            {
                                maximumProperty.SetValue(slider, maxValue.Value);
                                solveRelevantMutationCommitted = true;
                            }
                            catch
                            {
                                if (solveRelevantMutationCommitted != true)
                                    solveRelevantMutationCommitted = null;
                                throw;
                            }
                        }

                        // Set the value
                        var valueProperty = sliderType.GetProperty("Value")
                            ?? throw new InvalidOperationException("Slider value property unavailable");
                        try
                        {
                            valueProperty.SetValue(slider, newValue);
                            solveRelevantMutationCommitted = true;
                        }
                        catch
                        {
                            if (solveRelevantMutationCommitted != true)
                                solveRelevantMutationCommitted = null;
                            throw;
                        }

                        scheduleResult = RequestPostMutationSolve(gh.Document!, obj, requestSolve: true);
                        var solveOutcome = scheduleResult.Value;
                        var receipt = FinalizeSetValueReceipt(readinessReceiptId, solveOutcome);
                        RefreshCanvas(gh.Canvas!, scheduleSolution: false);

                        // Get the actual min/max for response
                        var actualMin = sliderType.GetProperty("Minimum")?.GetValue(slider);
                        var actualMax = sliderType.GetProperty("Maximum")?.GetValue(slider);

                        return new ApiResponse
                        {
                            Success = true,
                            Data = new
                            {
                                Guid = guid,
                                Type = "slider",
                                NewValue = newValue,
                                Min = actualMin,
                                Max = actualMax,
                                solve_relevant_mutation_committed = true,
                                solve_readiness_receipt = ReceiptSnapshot(receipt)
                            }
                        };
                    }
                }

                // Handle Panel
                if (typeName == "GH_Panel")
                {
                    var userTextProp = obj.GetType().GetProperty("UserText");
                    // Convert any JSON value type to string for panel
                    string newContent = valueEl.ValueKind switch
                    {
                        JsonValueKind.String => valueEl.GetString() ?? "",
                        JsonValueKind.Number => valueEl.GetRawText(),
                        JsonValueKind.True => "true",
                        JsonValueKind.False => "false",
                        JsonValueKind.Null => "",
                        _ => valueEl.GetRawText()
                    };
                    var issue = BeginSetValueReceipt(gh.Document!, gh.Canvas!);
                    if (!issue.Issued)
                        return ReadinessIssueFailure(issue.Error!);
                    readinessReceiptId = issue.Receipt!.ReceiptId;
                    mutationTarget = obj;

                    // Record generic undo after reservation and before changing the panel.
                    try
                    {
                        var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                        if (undoUtil != null)
                            RecordGenericObjectUndoEvent(undoUtil, "Rook: set value", obj);
                    }
                    catch { /* undo recording is best-effort */ }

                    if (userTextProp is null)
                        throw new InvalidOperationException("Panel value property unavailable");
                    try
                    {
                        userTextProp.SetValue(obj, newContent);
                        solveRelevantMutationCommitted = true;
                    }
                    catch
                    {
                        solveRelevantMutationCommitted = null;
                        throw;
                    }

                    scheduleResult = RequestPostMutationSolve(gh.Document!, obj, requestSolve: true);
                    var solveOutcome = scheduleResult.Value;
                    var receipt = FinalizeSetValueReceipt(readinessReceiptId, solveOutcome);
                    RefreshCanvas(gh.Canvas!, scheduleSolution: false);

                    return new ApiResponse
                    {
                        Success = true,
                        Data = new
                        {
                            Guid = guid,
                            Type = "panel",
                            NewValue = newContent,
                            solve_relevant_mutation_committed = true,
                            solve_readiness_receipt = ReceiptSnapshot(receipt)
                        }
                    };
                }

                // Handle Boolean Toggle
                if (typeName == "GH_BooleanToggle")
                {
                    var valueProp = obj.GetType().GetProperty("Value");
                    bool newValue = valueEl.GetBoolean();
                    var issue = BeginSetValueReceipt(gh.Document!, gh.Canvas!);
                    if (!issue.Issued)
                        return ReadinessIssueFailure(issue.Error!);
                    readinessReceiptId = issue.Receipt!.ReceiptId;
                    mutationTarget = obj;

                    // Record generic undo after reservation and before changing the toggle.
                    try
                    {
                        var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                        if (undoUtil != null)
                            RecordGenericObjectUndoEvent(undoUtil, "Rook: set value", obj);
                    }
                    catch { /* undo recording is best-effort */ }

                    if (valueProp is null)
                        throw new InvalidOperationException("Toggle value property unavailable");
                    try
                    {
                        valueProp.SetValue(obj, newValue);
                        solveRelevantMutationCommitted = true;
                    }
                    catch
                    {
                        solveRelevantMutationCommitted = null;
                        throw;
                    }

                    scheduleResult = RequestPostMutationSolve(gh.Document!, obj, requestSolve: true);
                    var solveOutcome = scheduleResult.Value;
                    var receipt = FinalizeSetValueReceipt(readinessReceiptId, solveOutcome);
                    RefreshCanvas(gh.Canvas!, scheduleSolution: false);

                    return new ApiResponse
                    {
                        Success = true,
                        Data = new
                        {
                            Guid = guid,
                            Type = "toggle",
                            NewValue = newValue,
                            solve_relevant_mutation_committed = true,
                            solve_readiness_receipt = ReceiptSnapshot(receipt)
                        }
                    };
                }

                return new ApiResponse
                {
                    Success = false,
                    Data = $"Unsupported object type for value set: {typeName}"
                };
            }
            catch (Exception ex)
            {
                if (readinessReceiptId is null)
                {
                    return new ApiResponse
                    {
                        Success = false,
                        Data = $"SetValue failed: {ex.Message}",
                    };
                }

                var receipt = FinalizePostReservationFailureReceipt(
                    readinessReceiptId,
                    solveRelevantMutationCommitted,
                    priorScheduleResult: scheduleResult,
                    scheduleCommittedMutation: mutationTarget is null
                        ? null
                        : () => RequestPostMutationSolve(
                            gh.Document!,
                            mutationTarget,
                            requestSolve: true));

                return new ApiResponse
                {
                    Success = false,
                    Data = DirectMutationFailureData(
                        "set_value_failed",
                        ex.Message,
                        solveRelevantMutationCommitted,
                        receipt),
                };
            }
        }

        /// <summary>
        /// POST /gh/script - Set or get the script source on a script component.
        /// Body: { guid: string, script?: string }
        /// If script is provided, sets it (SetSource). If omitted, returns current source (TryGetSource).
        /// Supports any component with SetSource/TryGetSource methods:
        ///   Python3Component, GhPythonComponent, CSharpScriptComponent, Component_CSNET_Script
        /// </summary>
        public ApiResponse SetScript(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_set_script");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_set_script", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            string? guid = null;
            string? script = null;
            string? readinessReceiptId = null;
            bool? solveRelevantMutationCommitted = false;
            object? mutationTarget = null;
            GhScheduleResult? scheduleResult = null;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args != null)
                {
                    if (args.TryGetValue("guid", out var g)) guid = g.GetString();
                    if (args.TryGetValue("script", out var s)) script = s.GetString();
                }
            }
            catch
            {
                return new ApiResponse { Success = false, Data = "Invalid body format" };
            }

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var obj = FindObjectById(gh.Document!, guid);
                if (obj == null)
                    return new ApiResponse { Success = false, Data = $"Object not found: {guid}" };

                var typeName = obj.GetType().Name;

                // Detect script component API capability via reflection:
                //   RhinoCode (Rhino 8+): SetSource(string) / TryGetSource(out string)
                //   GH1 legacy:           ScriptSource property with ScriptCode sub-property
                var setSourceMethod = obj.GetType().GetMethod("SetSource", new[] { typeof(string) });
                var tryGetSourceMethod = obj.GetType().GetMethod("TryGetSource");
                var scriptSourceProp = obj.GetType().GetProperty("ScriptSource",
                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);

                bool isRhinoCode = setSourceMethod != null || tryGetSourceMethod != null;
                bool isGh1Script = scriptSourceProp != null;

                if (!isRhinoCode && !isGh1Script)
                    return new ApiResponse { Success = false, Data = $"Not a script component (no SetSource or ScriptSource): {typeName}" };

                if (script == null)
                {
                    // --- READ ---
                    if (isRhinoCode && tryGetSourceMethod != null)
                    {
                        var parameters = new object?[] { null };
                        var success = (bool)(tryGetSourceMethod.Invoke(obj, parameters) ?? false);
                        if (!success)
                            return new ApiResponse { Success = false, Data = "Failed to retrieve script source" };
                        var currentSource = parameters[0] as string ?? "";
                        return new ApiResponse
                        {
                            Success = true,
                            Data = new { Guid = guid, Type = typeName, Action = "get", Script = currentSource, ScriptLength = currentSource.Length }
                        };
                    }
                    if (isGh1Script)
                    {
                        var sourceObj = scriptSourceProp!.GetValue(obj);
                        if (sourceObj != null)
                        {
                            var codeProp = sourceObj.GetType().GetProperty("ScriptCode");
                            var currentSource = codeProp?.GetValue(sourceObj) as string ?? "";
                            return new ApiResponse
                            {
                                Success = true,
                                Data = new { Guid = guid, Type = typeName, Action = "get", Script = currentSource, ScriptLength = currentSource.Length }
                            };
                        }
                    }
                    return new ApiResponse { Success = false, Data = $"Cannot read script from {typeName}" };
                }
                else
                {
                    // --- WRITE ---
                    var issue = BeginMutationReceipt(gh.Document!, gh.Canvas!);
                    if (!issue.Issued)
                        return ReadinessIssueFailure(issue.Error!);
                    readinessReceiptId = issue.Receipt!.ReceiptId;
                    mutationTarget = obj;

                    // Record generic undo BEFORE changing script
                    try
                    {
                        var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                        if (undoUtil != null)
                            RecordGenericObjectUndoEvent(undoUtil, "Rook: set script", obj);
                    }
                    catch { /* undo recording is best-effort */ }

                    // Capture existing pin descriptions BEFORE recompile. RhinoCode's recompile
                    // resets pin Description to the framework default ("No conversion"), so we
                    // save them and re-apply after ExpireSolution. Name-based FIFO matching
                    // (via ApplyPinDescriptions) is robust against duplicate pin names AND
                    // against any pin reordering a recompile might introduce — index-based
                    // matching would silently land descriptions on the wrong pin if the
                    // recompile ever shuffles params.
                    var savedInputDescriptions = CapturePinDescriptionsByName(obj, isInput: true);
                    var savedOutputDescriptions = CapturePinDescriptionsByName(obj, isInput: false, skipFirstN: 1);

                    if (isRhinoCode && setSourceMethod != null)
                    {
                        try
                        {
                            setSourceMethod.Invoke(obj, new object[] { script });
                            solveRelevantMutationCommitted = true;
                        }
                        catch
                        {
                            solveRelevantMutationCommitted = null;
                            throw;
                        }
                    }
                    else if (isGh1Script)
                    {
                        var sourceObj = scriptSourceProp!.GetValue(obj);
                        if (sourceObj != null)
                        {
                            var codeProp = sourceObj.GetType().GetProperty("ScriptCode");
                            if (codeProp != null && codeProp.CanWrite)
                            {
                                try
                                {
                                    codeProp.SetValue(sourceObj, script);
                                    solveRelevantMutationCommitted = true;
                                }
                                catch
                                {
                                    solveRelevantMutationCommitted = null;
                                    throw;
                                }
                            }
                            else
                            {
                                // Fallback: try field-level access
                                var codeField = sourceObj.GetType().GetField("ScriptCode",
                                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);
                                if (codeField != null)
                                {
                                    try
                                    {
                                        codeField.SetValue(sourceObj, script);
                                        solveRelevantMutationCommitted = true;
                                    }
                                    catch
                                    {
                                        solveRelevantMutationCommitted = null;
                                        throw;
                                    }
                                }
                                else
                                    throw new InvalidOperationException($"Cannot set script on {typeName}: ScriptCode not writable");
                            }
                        }
                        else
                        {
                            throw new InvalidOperationException($"ScriptSource is null on {typeName}");
                        }
                    }
                    else
                    {
                        throw new InvalidOperationException($"SetSource not available on {typeName}");
                    }

                    // Mark dirty without recompute before restoring metadata. Scheduling
                    // waits until the restored descriptions have been read back.
                    ExpirePostMutationDirtyObjects(new[] { obj });

                    // Restore saved descriptions — must happen AFTER recompile + ExpireSolution
                    // or they get clobbered back to framework defaults.
                    var restoreWarnings = new List<string>();
                    int restoredInputDescriptions = 0, droppedInputDescriptions = 0;
                    int restoredOutputDescriptions = 0, droppedOutputDescriptions = 0;

                    var paramsProp = obj.GetType().GetProperty("Params");
                    var paramsObjForRestore = paramsProp?.GetValue(obj);
                    if (paramsObjForRestore != null)
                    {
                        var inputListProp = paramsObjForRestore.GetType().GetProperty("Input");
                        var outputListProp = paramsObjForRestore.GetType().GetProperty("Output");
                        ApplyPinDescriptions(
                            inputListProp?.GetValue(paramsObjForRestore),
                            savedInputDescriptions,
                            "input",
                            restoreWarnings,
                            out restoredInputDescriptions,
                            out droppedInputDescriptions);
                        ApplyPinDescriptions(
                            outputListProp?.GetValue(paramsObjForRestore),
                            savedOutputDescriptions,
                            "output",
                            restoreWarnings,
                            out restoredOutputDescriptions,
                            out droppedOutputDescriptions,
                            skipFirstN: 1); // skip 'out' print stream
                    }

                    // Repaint only, then request exactly one asynchronous solve after
                    // all response-authoritative metadata has been restored.
                    RefreshCanvas(gh.Canvas!, scheduleSolution: false);
                    scheduleResult = RequestPostMutationSolve(
                        gh.Document!,
                        new[] { obj },
                        requestSolve: true,
                        expireDirtyObjects: false);
                    var solveResult = scheduleResult.Value;
                    var receipt = FinalizeMutationReceipt(readinessReceiptId, solveResult);

                    return new ApiResponse
                    {
                        Success = true,
                        Data = new
                        {
                            Guid = guid,
                            Type = typeName,
                            Action = "set",
                            ScriptLength = script.Length,
                            RestoredInputDescriptions = restoredInputDescriptions,
                            DroppedInputDescriptions = droppedInputDescriptions,
                            RestoredOutputDescriptions = restoredOutputDescriptions,
                            DroppedOutputDescriptions = droppedOutputDescriptions,
                            Warnings = restoreWarnings,
                            schedule_classification = GhScheduleWire.ToWire(solveResult.ScheduleClassification),
                            schedule_acceptance = GhScheduleWire.ToWire(solveResult.ScheduleAcceptance),
                            schedule_failure_code = solveResult.ScheduleFailureCode.HasValue
                                ? GhScheduleWire.ToWire(solveResult.ScheduleFailureCode.Value)
                                : null,
                            solve_scheduled = solveResult.SolveScheduled,
                            registration_known = solveResult.RegistrationKnown,
                            document_registered = solveResult.DocumentRegistered,
                            solver_locked = solveResult.SolverLocked,
                            solver_state_known = solveResult.SolverStateKnown,
                            verification_deferred = solveResult.VerificationDeferred,
                            solve_warnings = solveResult.Warnings.Select(GhScheduleWire.ToWire).ToArray(),
                            solve_relevant_mutation_committed = true,
                            solve_readiness_receipt = ReceiptSnapshot(receipt)
                        }
                    };
                }
            }
            catch (Exception ex)
            {
                if (readinessReceiptId is null)
                {
                    return new ApiResponse
                    {
                        Success = false,
                        Data = $"SetScript failed: {ex.Message}",
                    };
                }

                var receipt = FinalizePostReservationFailureReceipt(
                    readinessReceiptId,
                    solveRelevantMutationCommitted,
                    priorScheduleResult: scheduleResult,
                    scheduleCommittedMutation: mutationTarget is null
                        ? null
                        : () => RequestPostMutationSolve(
                            gh.Document!,
                            new[] { mutationTarget },
                            requestSolve: true,
                            expireDirtyObjects: false));

                return new ApiResponse
                {
                    Success = false,
                    Data = DirectMutationFailureData(
                        "set_script_failed",
                        ex.Message,
                        solveRelevantMutationCommitted,
                        receipt),
                };
            }
        }

        private static string? GetParamAccessString(object param)
        {
            var access = param.GetType().GetProperty("Access")?.GetValue(param);
            var raw = access?.ToString();
            return string.IsNullOrWhiteSpace(raw) ? null : raw.ToLowerInvariant();
        }

        private static bool? GetParamOptionalFlag(object param)
        {
            var optional = param.GetType().GetProperty("Optional")?.GetValue(param);
            return optional is bool value ? value : null;
        }

        private static Dictionary<string, Queue<List<object>>> CaptureNamedParamLinks(
            object? paramCollection,
            string linkPropertyName,
            int startIndex = 0)
        {
            var captured = new Dictionary<string, Queue<List<object>>>(StringComparer.OrdinalIgnoreCase);
            if (paramCollection == null)
                return captured;

            var collectionType = paramCollection.GetType();
            var count = (int)(collectionType.GetProperty("Count")?.GetValue(paramCollection) ?? 0);
            var indexer = collectionType.GetProperty("Item");
            for (int i = startIndex; i < count; i++)
            {
                var param = indexer?.GetValue(paramCollection, new object[] { i });
                if (param == null)
                    continue;

                var name = param.GetType().GetProperty("Name")?.GetValue(param) as string;
                if (string.IsNullOrWhiteSpace(name))
                    continue;

                var links = param.GetType().GetProperty(linkPropertyName)?.GetValue(param)
                    as System.Collections.IEnumerable;
                if (links == null)
                    continue;

                var linkList = links.Cast<object>().ToList();
                if (linkList.Count == 0)
                    continue;

                var key = name.Trim();
                if (!captured.TryGetValue(key, out var queue))
                {
                    queue = new Queue<List<object>>();
                    captured[key] = queue;
                }

                queue.Enqueue(linkList);
            }

            return captured;
        }

        private static List<object>? TakeCapturedParamLinks(
            Dictionary<string, Queue<List<object>>> capturedLinks,
            string paramName)
        {
            if (!capturedLinks.TryGetValue(paramName, out var queue) || queue.Count == 0)
                return null;

            var links = queue.Dequeue();
            if (queue.Count == 0)
                capturedLinks.Remove(paramName);

            return links;
        }

        private static void ReattachInputSources(
            object inputParam,
            string paramName,
            Dictionary<string, Queue<List<object>>> capturedSources,
            Type ighParamType,
            List<string> warnings,
            out int restoredCount,
            out int droppedCount)
        {
            restoredCount = 0;
            droppedCount = 0;
            var savedSources = TakeCapturedParamLinks(capturedSources, paramName);
            if (savedSources == null || savedSources.Count == 0)
                return;

            var addSourceMethod = inputParam.GetType().GetMethod("AddSource", new[] { ighParamType });
            if (addSourceMethod == null)
            {
                droppedCount = savedSources.Count;
                warnings.Add($"Failed to restore {savedSources.Count} source connection(s) for input '{paramName}': AddSource not found");
                return;
            }

            foreach (var source in savedSources)
            {
                try
                {
                    addSourceMethod.Invoke(inputParam, new[] { source });
                    restoredCount++;
                }
                catch (Exception ex)
                {
                    droppedCount++;
                    var message = ex.InnerException?.Message ?? ex.Message;
                    warnings.Add($"Failed to restore source connection for input '{paramName}': {message}");
                }
            }
        }

        private static void ReattachOutputRecipients(
            object outputParam,
            string paramName,
            Dictionary<string, Queue<List<object>>> capturedRecipients,
            Type ighParamType,
            List<string> warnings,
            out int restoredCount,
            out int droppedCount)
        {
            restoredCount = 0;
            droppedCount = 0;
            var savedRecipients = TakeCapturedParamLinks(capturedRecipients, paramName);
            if (savedRecipients == null || savedRecipients.Count == 0)
                return;

            foreach (var recipient in savedRecipients)
            {
                var addSourceMethod = recipient.GetType().GetMethod("AddSource", new[] { ighParamType });
                if (addSourceMethod == null)
                {
                    droppedCount++;
                    warnings.Add($"Failed to restore recipient connection for output '{paramName}': AddSource not found");
                    continue;
                }

                try
                {
                    addSourceMethod.Invoke(recipient, new[] { outputParam });
                    restoredCount++;
                }
                catch (Exception ex)
                {
                    droppedCount++;
                    var message = ex.InnerException?.Message ?? ex.Message;
                    warnings.Add($"Failed to restore recipient connection for output '{paramName}': {message}");
                }
            }
        }

        private static Dictionary<string, Queue<string>> CapturePinDescriptionsByName(
            object component,
            bool isInput,
            int skipFirstN = 0)
        {
            var result = new Dictionary<string, Queue<string>>(StringComparer.Ordinal);
            var paramsProp = component.GetType().GetProperty("Params");
            if (paramsProp == null) return result;
            var paramsObj = paramsProp.GetValue(component);
            if (paramsObj == null) return result;
            var listProp = paramsObj.GetType().GetProperty(isInput ? "Input" : "Output");
            if (listProp == null) return result;
            if (listProp.GetValue(paramsObj) is not System.Collections.IEnumerable list) return result;

            int idx = -1;
            foreach (var param in list)
            {
                idx++;
                if (idx < skipFirstN) continue;
                if (param == null) continue;
                var paramType = param.GetType();
                var name = paramType.GetProperty("Name")?.GetValue(param) as string;
                if (string.IsNullOrEmpty(name)) continue;
                var desc = paramType.GetProperty("Description")?.GetValue(param) as string;
                if (string.IsNullOrEmpty(desc)) continue;
                if (!result.TryGetValue(name, out var queue))
                {
                    queue = new Queue<string>();
                    result[name] = queue;
                }
                queue.Enqueue(desc);
            }
            return result;
        }

        private static void ApplyPinDescriptions(
            object? paramsCollection,
            Dictionary<string, Queue<string>> descriptionsByName,
            string direction,
            List<string> warnings,
            out int appliedCount,
            out int droppedCount,
            int skipFirstN = 0)
        {
            appliedCount = 0;
            droppedCount = 0;

            if (descriptionsByName.Count == 0)
                return;

            if (paramsCollection is System.Collections.IEnumerable enumerable)
            {
                int index = -1;
                foreach (var param in enumerable)
                {
                    index++;
                    if (index < skipFirstN)
                        continue;
                    if (param == null)
                        continue;
                    var paramType = param.GetType();
                    var nameValue = paramType.GetProperty("Name")?.GetValue(param) as string;
                    if (nameValue == null ||
                        !descriptionsByName.TryGetValue(nameValue, out var queue) ||
                        queue.Count == 0)
                        continue;
                    var description = queue.Dequeue();
                    try
                    {
                        var descriptionProp = paramType.GetProperty("Description");
                        if (descriptionProp?.CanWrite == true)
                        {
                            descriptionProp.SetValue(param, description);
                            appliedCount++;
                        }
                        else
                        {
                            droppedCount++;
                            warnings.Add($"Could not set description on {direction} '{nameValue}': Description property not writable");
                        }
                    }
                    catch (Exception ex)
                    {
                        droppedCount++;
                        var message = ex.InnerException?.Message ?? ex.Message;
                        warnings.Add($"Failed to set description on {direction} '{nameValue}': {message}");
                    }
                    if (queue.Count == 0)
                        descriptionsByName.Remove(nameValue);
                }
            }

            // Any descriptions left in queues had no matching param (renamed-out pin, typo).
            foreach (var kvp in descriptionsByName)
            {
                if (kvp.Value.Count == 0)
                    continue;
                droppedCount += kvp.Value.Count;
                warnings.Add($"Could not set description: no matching {direction} named '{kvp.Key}' (dropped {kvp.Value.Count})");
            }
        }

        // Pre-validates a script pin definition BEFORE any destructive component
        // mutation. Mirrors the runtime checks in TryApplyScriptPinDefinition plus
        // the JSON type checks that were previously implicit (and threw post-unregister).
        // See issue #39. Existing error text for pre-existing branches is preserved.
        private static string? ValidateScriptPinDef(JsonElement pinDef, int idx, string direction)
        {
            if (pinDef.ValueKind != JsonValueKind.Object)
                return $"{direction} pin at index {idx} must be an object";

            if (!pinDef.TryGetProperty("name", out var nameEl))
                return "Pin definition is missing 'name'";
            if (nameEl.ValueKind != JsonValueKind.String)
                return $"{direction} pin at index {idx}: 'name' must be a string";
            var name = nameEl.GetString();
            if (string.IsNullOrWhiteSpace(name))
                return "Pin definition has an empty 'name'";

            if (pinDef.TryGetProperty("nick", out var nickEl)
                && nickEl.ValueKind != JsonValueKind.String
                && nickEl.ValueKind != JsonValueKind.Null)
                return $"{direction} pin '{name}': 'nick' must be a string when present";

            if (pinDef.TryGetProperty("current_name", out var currentNameEl)
                && currentNameEl.ValueKind != JsonValueKind.String
                && currentNameEl.ValueKind != JsonValueKind.Null)
                return $"{direction} pin '{name}': 'current_name' must be a string when present";

            if (pinDef.TryGetProperty("access", out var accessEl))
            {
                if (accessEl.ValueKind != JsonValueKind.String && accessEl.ValueKind != JsonValueKind.Null)
                    return $"{direction} pin '{name}': 'access' must be a string when present";
                var accessText = accessEl.GetString()?.Trim().ToLowerInvariant();
                if (!string.IsNullOrWhiteSpace(accessText)
                    && accessText != "item" && accessText != "single"
                    && accessText != "list" && accessText != "tree")
                    return $"Invalid access '{accessText}' for pin '{name}'";
            }

            if (pinDef.TryGetProperty("description", out var descriptionEl)
                && descriptionEl.ValueKind != JsonValueKind.String
                && descriptionEl.ValueKind != JsonValueKind.Null)
                return $"{direction} pin '{name}': 'description' must be a string when present";

            return null;
        }

        private static bool TryApplyScriptPinDefinition(
            object param,
            JsonElement pinDef,
            bool isInput,
            out string error)
        {
            error = string.Empty;

            if (!pinDef.TryGetProperty("name", out var nameEl))
            {
                error = "Pin definition is missing 'name'";
                return false;
            }

            var name = nameEl.GetString();
            if (string.IsNullOrWhiteSpace(name))
            {
                error = "Pin definition has an empty 'name'";
                return false;
            }

            var paramType = param.GetType();
            var nick = pinDef.TryGetProperty("nick", out var nickEl)
                ? nickEl.GetString()
                : name;

            paramType.GetProperty("Name")?.SetValue(param, name);
            paramType.GetProperty("NickName")?.SetValue(param, string.IsNullOrWhiteSpace(nick) ? name : nick);

            if (pinDef.TryGetProperty("access", out var accessEl))
            {
                var accessText = accessEl.GetString()?.Trim().ToLowerInvariant();
                if (!string.IsNullOrWhiteSpace(accessText))
                {
                    var accessProp = paramType.GetProperty("Access");
                    if (accessProp?.CanWrite == true)
                    {
                        object? accessValue = accessText switch
                        {
                            "item" or "single" => Enum.ToObject(accessProp.PropertyType, 0),
                            "list" => Enum.ToObject(accessProp.PropertyType, 1),
                            "tree" => Enum.ToObject(accessProp.PropertyType, 2),
                            _ => null
                        };

                        if (accessValue == null)
                        {
                            error = $"Invalid access '{accessText}' for pin '{name}'";
                            return false;
                        }

                        accessProp.SetValue(param, accessValue);
                    }
                }
            }

            if (pinDef.TryGetProperty("optional", out var optionalEl) &&
                optionalEl.ValueKind is JsonValueKind.True or JsonValueKind.False)
            {
                var optionalProp = paramType.GetProperty("Optional");
                if (optionalProp?.CanWrite == true)
                    optionalProp.SetValue(param, optionalEl.GetBoolean());
            }
            else if (isInput)
            {
                var optionalProp = paramType.GetProperty("Optional");
                if (optionalProp?.CanWrite == true)
                    optionalProp.SetValue(param, true);
            }

            if (pinDef.TryGetProperty("description", out var descriptionEl))
            {
                var description = descriptionEl.GetString();
                var descriptionProp = paramType.GetProperty("Description");
                if (descriptionProp?.CanWrite == true)
                    descriptionProp.SetValue(param, description ?? string.Empty);
            }

            if (pinDef.TryGetProperty("hidden", out var hiddenEl) &&
                hiddenEl.ValueKind is JsonValueKind.True or JsonValueKind.False)
            {
                var hiddenProp = paramType.GetProperty("Hidden");
                if (hiddenProp?.CanWrite == true)
                    hiddenProp.SetValue(param, hiddenEl.GetBoolean());
            }

            return true;
        }

        /// <summary>
        /// POST /gh/script-params - Configure input/output parameters on a script component.
        /// Body: { guid: string, inputs: [{name, nick?, access?, optional?, description?, hidden?}], outputs: [...] }
        /// Replaces all variable inputs and outputs (keeps 'out' print stream).
        /// </summary>
        internal ApiResponse ScriptParams(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_set_script_pins");
            if (notReady != null)
                return notReady;

            try
            {
                var gh = GetGrasshopper();
                if (!gh.Success)
                    return GrasshopperNotReadyResponse("gh_set_script_pins", null, gh.Error);

                if (string.IsNullOrWhiteSpace(body))
                    return new ApiResponse { Success = false, Data = "Missing request body" };

                using var jsonDoc = JsonDocument.Parse(body);
                var root = jsonDoc.RootElement;

                if (!root.TryGetProperty("guid", out var guidEl))
                    return new ApiResponse { Success = false, Data = "Missing guid parameter" };
                if (guidEl.ValueKind != JsonValueKind.String)
                    return new ApiResponse { Success = false, Data = "'guid' must be a string" };

                var guid = guidEl.GetString()!;
                var obj = FindObjectById(gh.Document, guid);
                if (obj == null)
                    return new ApiResponse { Success = false, Data = $"Object not found: {guid}" };

                var objType = obj.GetType();
                var typeName = objType.Name;

                // Check for Params property (IGH_Component)
                var paramsProp = objType.GetProperty("Params");
                if (paramsProp == null)
                    return new ApiResponse { Success = false, Data = $"Not a component (no Params): {typeName}" };

                var paramsObj = paramsProp.GetValue(obj);
                if (paramsObj == null)
                    return new ApiResponse { Success = false, Data = $"Params is null: {typeName}" };

                // Check for IGH_VariableParameterComponent via VariableParameterMaintenance method
                var maintMethod = objType.GetMethod("VariableParameterMaintenance");
                if (maintMethod == null)
                    return new ApiResponse { Success = false, Data = $"Not a variable-parameter component: {typeName}" };

                var paramsType = paramsObj.GetType();

                // Get Input and Output lists
                var inputProp = paramsType.GetProperty("Input");
                var outputProp = paramsType.GetProperty("Output");
                if (inputProp == null || outputProp == null)
                    return new ApiResponse { Success = false, Data = $"Cannot access Input/Output params: {typeName}" };

                var ighParamType = gh.Assembly!.GetType("Grasshopper.Kernel.IGH_Param");
                if (ighParamType == null)
                    return new ApiResponse { Success = false, Data = "Grasshopper.Kernel.IGH_Param type not found" };

                var paramElementType = inputProp.PropertyType.IsGenericType
                    ? inputProp.PropertyType.GetGenericArguments()[0]
                    : typeof(object);
                var unregInput = paramsType.GetMethod("UnregisterInputParameter",
                    new[] { paramElementType });
                var unregOutput = paramsType.GetMethod("UnregisterOutputParameter",
                    new[] { outputProp.PropertyType.IsGenericType
                        ? outputProp.PropertyType.GetGenericArguments()[0]
                        : paramElementType });
                var regInput = paramsType.GetMethod("RegisterInputParam",
                    BindingFlags.Public | BindingFlags.Instance,
                    null, new Type[] { paramElementType }, null);
                var regOutput = paramsType.GetMethod("RegisterOutputParam",
                    BindingFlags.Public | BindingFlags.Instance,
                    null, new Type[] { outputProp.PropertyType.IsGenericType
                        ? outputProp.PropertyType.GetGenericArguments()[0]
                        : paramElementType }, null);

                // C4: Fail early if any registration method is missing
                if (unregInput == null || unregOutput == null || regInput == null || regOutput == null)
                    return new ApiResponse
                    {
                        Success = false,
                        Data = $"Cannot find parameter registration methods on {paramsType.Name}: " +
                               $"UnregIn={unregInput != null}, UnregOut={unregOutput != null}, " +
                               $"RegIn={regInput != null}, RegOut={regOutput != null}"
                    };

                // Use CreateParameter from IGH_VariableParameterComponent to create
                // the correct parameter type for this component (e.g. ScriptVariableParam
                // for RhinoCode, Param_GenericObject for standard ZUI components).
                // GH_ParameterSide: Input=0, Output=1
                var createParamMethod = objType.GetMethod("CreateParameter",
                    BindingFlags.Public | BindingFlags.Instance);
                Type? paramSideType = null;
                if (createParamMethod != null)
                {
                    var cpParams = createParamMethod.GetParameters();
                    if (cpParams.Length >= 2)
                        paramSideType = cpParams[0].ParameterType; // GH_ParameterSide enum
                }

                if (createParamMethod == null || paramSideType == null)
                    return new ApiResponse { Success = false, Data = $"Cannot find CreateParameter on {typeName}" };

                var sideInput = Enum.ToObject(paramSideType, 0);   // GH_ParameterSide.Input
                var sideOutput = Enum.ToObject(paramSideType, 1);  // GH_ParameterSide.Output
                var restoreWarnings = new List<string>();
                int restoredInputSourceCount = 0;
                int droppedInputSourceCount = 0;
                int restoredOutputRecipientCount = 0;
                int droppedOutputRecipientCount = 0;

                // Pre-validate all user-provided JSON BEFORE any destructive mutation.
                // See issue #39 — previously, invalid fields (non-string name/access/nick/
                // current_name/description or non-array inputs/outputs) threw inside the
                // unregister→reregister loops below, leaving the component stripped and
                // surfacing as a generic "ScriptParams failed" via the top-level catch.
                // Now: all shape + value checks run first; any failure returns
                // Success=false with the component untouched.
                if (root.TryGetProperty("nick", out var rootNickEl)
                    && rootNickEl.ValueKind != JsonValueKind.String
                    && rootNickEl.ValueKind != JsonValueKind.Null)
                    return new ApiResponse { Success = false, Data = "'nick' must be a string when present" };

                if (root.TryGetProperty("inputs", out var preInputsEl))
                {
                    if (preInputsEl.ValueKind != JsonValueKind.Array)
                        return new ApiResponse { Success = false, Data = "'inputs' must be an array when present" };
                    int pinIdx = 0;
                    foreach (var pinDef in preInputsEl.EnumerateArray())
                    {
                        var err = ValidateScriptPinDef(pinDef, pinIdx, "input");
                        if (err != null)
                            return new ApiResponse { Success = false, Data = err };
                        pinIdx++;
                    }
                }
                if (root.TryGetProperty("outputs", out var preOutputsEl))
                {
                    if (preOutputsEl.ValueKind != JsonValueKind.Array)
                        return new ApiResponse { Success = false, Data = "'outputs' must be an array when present" };
                    int pinIdx = 0;
                    foreach (var pinDef in preOutputsEl.EnumerateArray())
                    {
                        var err = ValidateScriptPinDef(pinDef, pinIdx, "output");
                        if (err != null)
                            return new ApiResponse { Success = false, Data = err };
                        pinIdx++;
                    }
                }

                // Remove all existing inputs (iterate backwards)
                var inputs = inputProp.GetValue(paramsObj);
                var capturedInputSources = CaptureNamedParamLinks(inputs, "Sources");
                var inputCount = (int)(inputs?.GetType().GetProperty("Count")?.GetValue(inputs) ?? 0);
                var inputIndexer = inputs?.GetType().GetProperty("Item");
                for (int i = inputCount - 1; i >= 0; i--)
                {
                    var param = inputIndexer?.GetValue(inputs, new object[] { i });
                    if (param != null)
                        unregInput.Invoke(paramsObj, new[] { param });
                }

                // Remove all existing outputs except index 0 ('out' — print stream)
                var outputs = outputProp.GetValue(paramsObj);
                var capturedOutputRecipients = CaptureNamedParamLinks(outputs, "Recipients", startIndex: 1);
                var outputCount = (int)(outputs?.GetType().GetProperty("Count")?.GetValue(outputs) ?? 0);
                var outputIndexer = outputs?.GetType().GetProperty("Item");
                for (int i = outputCount - 1; i >= 1; i--)
                {
                    var param = outputIndexer?.GetValue(outputs, new object[] { i });
                    if (param != null)
                        unregOutput.Invoke(paramsObj, new[] { param });
                }

                // RhinoCode's VariableParameterMaintenance and SetSource recompile both
                // reset pin Description to the framework default ("No conversion"), so we
                // defer description application to AFTER the recompile/maintenance chain.
                // FIFO queue per name handles the edge case of two pins sharing a Name.
                var pendingInputDescriptions = new Dictionary<string, Queue<string>>(StringComparer.Ordinal);
                var pendingOutputDescriptions = new Dictionary<string, Queue<string>>(StringComparer.Ordinal);

                // Add new inputs using CreateParameter (gets correct param type)
                if (root.TryGetProperty("inputs", out var inputsEl))
                {
                    int idx = 0;
                    foreach (var inputDef in inputsEl.EnumerateArray())
                    {
                        var name = inputDef.TryGetProperty("name", out var nameEl)
                            ? nameEl.GetString() ?? $"Input{idx}"
                            : $"Input{idx}";
                        var lookupName = inputDef.TryGetProperty("current_name", out var currentNameEl) &&
                                         !string.IsNullOrWhiteSpace(currentNameEl.GetString())
                            ? currentNameEl.GetString()!
                            : name;
                        var newParam = createParamMethod.Invoke(obj, new[] { sideInput, idx });
                        if (newParam == null)
                            return new ApiResponse { Success = false, Data = $"CreateParameter returned null for input '{name}'" };
                        if (!TryApplyScriptPinDefinition(newParam, inputDef, isInput: true, out var error))
                            return new ApiResponse { Success = false, Data = error };
                        if (inputDef.TryGetProperty("description", out var descEl) &&
                            descEl.ValueKind == JsonValueKind.String)
                        {
                            if (!pendingInputDescriptions.TryGetValue(name, out var queue))
                            {
                                queue = new Queue<string>();
                                pendingInputDescriptions[name] = queue;
                            }
                            queue.Enqueue(descEl.GetString() ?? string.Empty);
                        }
                        regInput.Invoke(paramsObj, new[] { newParam });
                        ReattachInputSources(
                            newParam,
                            lookupName,
                            capturedInputSources,
                            ighParamType,
                            restoreWarnings,
                            out var restoredCount,
                            out var droppedCount);
                        restoredInputSourceCount += restoredCount;
                        droppedInputSourceCount += droppedCount;
                        idx++;
                    }
                }

                // Add new outputs using CreateParameter
                if (root.TryGetProperty("outputs", out var outputsEl))
                {
                    int idx = 1; // index 0 is the 'out' print stream
                    foreach (var outputDef in outputsEl.EnumerateArray())
                    {
                        var name = outputDef.TryGetProperty("name", out var nameEl)
                            ? nameEl.GetString() ?? $"Output{idx}"
                            : $"Output{idx}";
                        var lookupName = outputDef.TryGetProperty("current_name", out var currentNameEl) &&
                                         !string.IsNullOrWhiteSpace(currentNameEl.GetString())
                            ? currentNameEl.GetString()!
                            : name;
                        var newParam = createParamMethod.Invoke(obj, new[] { sideOutput, idx });
                        if (newParam == null)
                            return new ApiResponse { Success = false, Data = $"CreateParameter returned null for output '{name}'" };
                        if (!TryApplyScriptPinDefinition(newParam, outputDef, isInput: false, out var error))
                            return new ApiResponse { Success = false, Data = error };
                        if (outputDef.TryGetProperty("description", out var descEl) &&
                            descEl.ValueKind == JsonValueKind.String)
                        {
                            if (!pendingOutputDescriptions.TryGetValue(name, out var queue))
                            {
                                queue = new Queue<string>();
                                pendingOutputDescriptions[name] = queue;
                            }
                            queue.Enqueue(descEl.GetString() ?? string.Empty);
                        }
                        regOutput.Invoke(paramsObj, new[] { newParam });
                        ReattachOutputRecipients(
                            newParam,
                            lookupName,
                            capturedOutputRecipients,
                            ighParamType,
                            restoreWarnings,
                            out var restoredCount,
                            out var droppedCount);
                        restoredOutputRecipientCount += restoredCount;
                        droppedOutputRecipientCount += droppedCount;
                        idx++;
                    }
                }

                // Set NickName if provided
                if (root.TryGetProperty("nick", out var nickEl))
                {
                    var nickVal = nickEl.GetString();
                    if (nickVal != null)
                        objType.GetProperty("NickName")?.SetValue(obj, nickVal);
                }

                // Defer component Description until after maintenance — same reset behavior
                // observed on pin descriptions applies to the component Description.
                string? pendingComponentDescription = null;
                if (root.TryGetProperty("description", out var descriptionEl) &&
                    descriptionEl.ValueKind == JsonValueKind.String)
                {
                    pendingComponentDescription = descriptionEl.GetString() ?? string.Empty;
                }

                // Finalize
                maintMethod.Invoke(obj, null);
                paramsType.GetMethod("OnParametersChanged")?.Invoke(paramsObj, null);

                // Force RhinoCode script recompilation so RunScript parameter bindings
                // match the new pin configuration. Without this, the compiled script
                // has stale bindings and won't re-solve when upstream inputs change.
                var tryGetSource = objType.GetMethod("TryGetSource");
                var setSource = objType.GetMethod("SetSource", new[] { typeof(string) });
                if (tryGetSource != null && setSource != null)
                {
                    var sourceArgs = new object?[] { null };
                    var gotSource = (bool)(tryGetSource.Invoke(obj, sourceArgs) ?? false);
                    if (gotSource && sourceArgs[0] is string currentSource)
                    {
                        setSource.Invoke(obj, new object[] { currentSource });
                    }
                }

                objType.GetMethod("ExpireSolution", new[] { typeof(bool) })?.Invoke(obj, new object[] { true });

                // Re-apply pin and component descriptions AFTER maintenance + recompile.
                // VariableParameterMaintenance and RhinoCode SetSource both reset Description
                // back to the framework default, so the value has to be stamped last to stick.
                int appliedInputDescriptions = 0, droppedInputDescriptions = 0;
                int appliedOutputDescriptions = 0, droppedOutputDescriptions = 0;
                bool componentDescriptionApplied = false;

                ApplyPinDescriptions(
                    inputProp.GetValue(paramsObj),
                    pendingInputDescriptions,
                    "input",
                    restoreWarnings,
                    out appliedInputDescriptions,
                    out droppedInputDescriptions);
                ApplyPinDescriptions(
                    outputProp.GetValue(paramsObj),
                    pendingOutputDescriptions,
                    "output",
                    restoreWarnings,
                    out appliedOutputDescriptions,
                    out droppedOutputDescriptions,
                    skipFirstN: 1); // skip 'out' print stream (always index 0)

                if (pendingComponentDescription != null)
                {
                    try
                    {
                        var descriptionProp = objType.GetProperty("Description");
                        if (descriptionProp?.CanWrite == true)
                        {
                            descriptionProp.SetValue(obj, pendingComponentDescription);
                            componentDescriptionApplied = true;
                        }
                        else
                        {
                            restoreWarnings.Add("Could not set component description: Description property not writable");
                        }
                    }
                    catch (Exception ex)
                    {
                        var message = ex.InnerException?.Message ?? ex.Message;
                        restoreWarnings.Add($"Failed to set component description: {message}");
                    }
                }

                if (gh.Canvas != null)
                    RefreshCanvas(gh.Canvas);

                // Re-read counts after modification
                inputs = inputProp.GetValue(paramsObj);
                outputs = outputProp.GetValue(paramsObj);
                var finalInputCount = (int)(inputs?.GetType().GetProperty("Count")?.GetValue(inputs) ?? 0);
                var finalOutputCount = (int)(outputs?.GetType().GetProperty("Count")?.GetValue(outputs) ?? 0);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Guid = guid,
                        Inputs = finalInputCount,
                        Outputs = finalOutputCount,
                        RestoredInputSources = restoredInputSourceCount,
                        DroppedInputSources = droppedInputSourceCount,
                        RestoredOutputRecipients = restoredOutputRecipientCount,
                        DroppedOutputRecipients = droppedOutputRecipientCount,
                        AppliedInputDescriptions = appliedInputDescriptions,
                        DroppedInputDescriptions = droppedInputDescriptions,
                        AppliedOutputDescriptions = appliedOutputDescriptions,
                        DroppedOutputDescriptions = droppedOutputDescriptions,
                        ComponentDescriptionApplied = componentDescriptionApplied,
                        Warnings = restoreWarnings
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"ScriptParams failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/set-reference - Set a Rhino geometry object as persistent data on a GH parameter
        /// Body: { guid: string (GH parameter component), rhinoId: string (Rhino object GUID) }
        /// Supports: Param_Curve, Param_Point, Param_Surface, Param_Brep, Param_Geometry, Param_Mesh
        /// </summary>
        public ApiResponse SetReference(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_set_reference");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_set_reference", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            string? guid = null;
            string? rhinoId = null;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args != null)
                {
                    // Accept both naming conventions
                    if (args.TryGetValue("guid", out var g)) guid = g.GetString();
                    else if (args.TryGetValue("paramGuid", out g)) guid = g.GetString();
                    if (args.TryGetValue("rhinoId", out var r)) rhinoId = r.GetString();
                    else if (args.TryGetValue("rhinoObjectId", out r)) rhinoId = r.GetString();
                }
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid body format: {ex.Message}. Body was: {body}" };
            }

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = $"Missing guid parameter. Body was: {body}" };
            if (string.IsNullOrEmpty(rhinoId))
                return new ApiResponse { Success = false, Data = "Missing rhinoId parameter" };

            try
            {
                // Find the GH parameter component
                var param = FindObjectById(gh.Document!, guid);
                if (param == null)
                    return new ApiResponse { Success = false, Data = $"GH parameter not found: {guid}" };

                var typeName = param.GetType().Name;

                // Get the Rhino object
                if (!Guid.TryParse(rhinoId, out var rhinoGuid))
                    return new ApiResponse { Success = false, Data = $"Invalid Rhino GUID: {rhinoId}" };

                var rhinoObj = DocumentContext.GetDocument()?.Objects.FindId(rhinoGuid);
                if (rhinoObj == null)
                    return new ApiResponse { Success = false, Data = $"Rhino object not found: {rhinoId}" };

                var geometry = rhinoObj.Geometry;
                if (geometry == null)
                    return new ApiResponse { Success = false, Data = "Rhino object has no geometry" };

                // Get PersistentData property
                var persistentDataProp = param.GetType().GetProperty("PersistentData");
                if (persistentDataProp == null)
                    return new ApiResponse { Success = false, Data = $"Component {typeName} does not support persistent data" };

                var persistentData = persistentDataProp.GetValue(param);
                if (persistentData == null)
                    return new ApiResponse { Success = false, Data = "Could not get persistent data" };

                // Clear existing data
                var clearMethod = persistentData.GetType().GetMethod("Clear");
                clearMethod?.Invoke(persistentData, null);

                // Create appropriate GH wrapper based on geometry type and parameter type
                object? ghWrapper = null;
                string geometryType = "";

                // Get the Grasshopper.Kernel.Types namespace
                var ghTypesAssembly = gh.Assembly!;

                if (typeName == "Param_Curve" && geometry is Rhino.Geometry.Curve curve)
                {
                    var ghCurveType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Curve");
                    if (ghCurveType != null)
                    {
                        ghWrapper = Activator.CreateInstance(ghCurveType, curve);
                        geometryType = "Curve";
                    }
                }
                else if (typeName == "Param_Point" && geometry is Rhino.Geometry.Point point)
                {
                    var ghPointType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Point");
                    if (ghPointType != null)
                    {
                        ghWrapper = Activator.CreateInstance(ghPointType, point.Location);
                        geometryType = "Point";
                    }
                }
                else if (typeName == "Param_Surface" && geometry is Rhino.Geometry.BrepFace face)
                {
                    var ghSurfaceType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Surface");
                    if (ghSurfaceType != null)
                    {
                        ghWrapper = Activator.CreateInstance(ghSurfaceType, face);
                        geometryType = "Surface";
                    }
                }
                else if (typeName == "Param_Brep" && geometry is Rhino.Geometry.Brep brep)
                {
                    var ghBrepType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Brep");
                    if (ghBrepType != null)
                    {
                        ghWrapper = Activator.CreateInstance(ghBrepType, brep);
                        geometryType = "Brep";
                    }
                }
                else if (typeName == "Param_Mesh" && geometry is Rhino.Geometry.Mesh mesh)
                {
                    var ghMeshType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Mesh");
                    if (ghMeshType != null)
                    {
                        ghWrapper = Activator.CreateInstance(ghMeshType, mesh);
                        geometryType = "Mesh";
                    }
                }
                else if (typeName == "Param_Geometry")
                {
                    // Generic geometry param can accept various types
                    var ghGeomType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_GeometricGoo`1");

                    // Try to wrap based on actual geometry type
                    if (geometry is Rhino.Geometry.Curve crv)
                    {
                        var ghCurveType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Curve");
                        if (ghCurveType != null)
                        {
                            ghWrapper = Activator.CreateInstance(ghCurveType, crv);
                            geometryType = "Curve";
                        }
                    }
                    else if (geometry is Rhino.Geometry.Brep b)
                    {
                        var ghBrepType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Brep");
                        if (ghBrepType != null)
                        {
                            ghWrapper = Activator.CreateInstance(ghBrepType, b);
                            geometryType = "Brep";
                        }
                    }
                    else if (geometry is Rhino.Geometry.Mesh m)
                    {
                        var ghMeshType = ghTypesAssembly.GetType("Grasshopper.Kernel.Types.GH_Mesh");
                        if (ghMeshType != null)
                        {
                            ghWrapper = Activator.CreateInstance(ghMeshType, m);
                            geometryType = "Mesh";
                        }
                    }
                }

                if (ghWrapper == null)
                    return new ApiResponse
                    {
                        Success = false,
                        Data = $"Cannot set {geometry.GetType().Name} on {typeName}. Type mismatch or unsupported combination."
                    };

                // Stamp ReferenceID so gh_get_reference and other wrapper introspection paths
                // see the wrapper as tied to a real Rhino doc object. Without this stamp, wrappers
                // start with ReferenceID == Guid.Empty, and gh_get_reference's
                // `refId.ToString() != Guid.Empty.ToString()` check at ~line 1500 treats them as
                // unreferenced local geometry. Defensive: only write if the property exists,
                // is writable, and is a Guid type — best-effort on failure since the wrapper
                // still holds geometry by value.
                //
                // NOTE: This does NOT fix issue #45 (RhinoCode Python 3 list-access emits
                // ephemeral random guids that don't correspond to ReferenceID). That needs a
                // separate preamble-level workaround using ghenv.Component.Params.Input[i].VolatileData
                // to read raw wrappers before RhinoCode's automatic guid-conversion.
                //
                // WARNING: Do NOT "helpfully" add a LoadGeometry() call here. Stamping ReferenceID
                // alone is deliberate — the wrapper keeps the by-value geometry we just constructed
                // and advertises doc identity for introspection only. LoadGeometry() would force
                // GH to re-fetch from the active doc, which could fail if the object is deleted
                // between set and solve.
                try
                {
                    var refIdProp = ghWrapper.GetType().GetProperty("ReferenceID");
                    if (refIdProp?.CanWrite == true && refIdProp.PropertyType == typeof(Guid))
                        refIdProp.SetValue(ghWrapper, rhinoGuid);
                }
                catch
                {
                    // best-effort
                }

                // Append to persistent data
                var appendMethod = persistentData.GetType().GetMethod("Append", new[] { ghWrapper.GetType().BaseType ?? ghWrapper.GetType() });
                if (appendMethod == null)
                {
                    // Try finding a generic Append method
                    var methods = persistentData.GetType().GetMethods().Where(m => m.Name == "Append").ToList();
                    foreach (var m in methods)
                    {
                        var parameters = m.GetParameters();
                        if (parameters.Length == 1)
                        {
                            try
                            {
                                m.Invoke(persistentData, new[] { ghWrapper });
                                appendMethod = m;
                                break;
                            }
                            catch { }
                        }
                    }
                }
                else
                {
                    appendMethod.Invoke(persistentData, new[] { ghWrapper });
                }

                // Expire the solution
                var expireMethod = param.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
                expireMethod?.Invoke(param, new object[] { true });

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Guid = guid,
                        RhinoId = rhinoId,
                        ParameterType = typeName,
                        GeometryType = geometryType,
                        Message = $"Set {geometryType} reference on {typeName}"
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"SetReference failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// GET /gh/get-reference - Get the persistent geometry references from a GH parameter
        /// Query: ?guid=...
        /// Returns list of Rhino object IDs referenced by this parameter
        /// </summary>
        public ApiResponse GetReference(string? guid)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_get_reference");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_get_reference", null, gh.Error);

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var param = FindObjectById(gh.Document!, guid);
                if (param == null)
                    return new ApiResponse { Success = false, Data = $"GH parameter not found: {guid}" };

                var typeName = param.GetType().Name;

                // Get PersistentData property
                var persistentDataProp = param.GetType().GetProperty("PersistentData");
                if (persistentDataProp == null)
                    return new ApiResponse { Success = false, Data = $"Component {typeName} does not support persistent data" };

                var persistentData = persistentDataProp.GetValue(param);
                if (persistentData == null)
                    return new ApiResponse { Success = true, Data = new { Guid = guid, References = new List<object>() } };

                // Get the data from PersistentData
                var references = new List<object>();

                // Try to enumerate the persistent data
                if (persistentData is System.Collections.IEnumerable enumerable)
                {
                    foreach (var item in enumerable)
                    {
                        // Try to get ReferenceID or the underlying geometry
                        var refIdProp = item.GetType().GetProperty("ReferenceID");
                        var valueProp = item.GetType().GetProperty("Value");

                        var refInfo = new Dictionary<string, object?>();

                        if (refIdProp != null)
                        {
                            var refId = refIdProp.GetValue(item);
                            if (refId != null && refId.ToString() != Guid.Empty.ToString())
                            {
                                refInfo["rhinoId"] = refId.ToString();
                            }
                        }

                        if (valueProp != null)
                        {
                            var value = valueProp.GetValue(item);
                            if (value != null)
                            {
                                refInfo["geometryType"] = value.GetType().Name;
                            }
                        }

                        refInfo["wrapperType"] = item.GetType().Name;
                        references.Add(refInfo);
                    }
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Guid = guid,
                        ParameterType = typeName,
                        ReferenceCount = references.Count,
                        References = references
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"GetReference failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/clear-reference - Clear all persistent references from a GH parameter
        /// Body: { guid: string }
        /// </summary>
        public ApiResponse ClearReference(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_clear_reference");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_clear_reference", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            string? guid = null;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args != null && args.TryGetValue("guid", out var g))
                    guid = g.GetString();
            }
            catch
            {
                return new ApiResponse { Success = false, Data = "Invalid body format" };
            }

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var param = FindObjectById(gh.Document!, guid);
                if (param == null)
                    return new ApiResponse { Success = false, Data = $"GH parameter not found: {guid}" };

                var typeName = param.GetType().Name;

                // Get PersistentData property
                var persistentDataProp = param.GetType().GetProperty("PersistentData");
                if (persistentDataProp == null)
                    return new ApiResponse { Success = false, Data = $"Component {typeName} does not support persistent data" };

                var persistentData = persistentDataProp.GetValue(param);
                if (persistentData == null)
                    return new ApiResponse { Success = true, Data = new { Guid = guid, Message = "No persistent data to clear" } };

                // Clear the data
                var clearMethod = persistentData.GetType().GetMethod("Clear");
                clearMethod?.Invoke(persistentData, null);

                // Expire the solution
                var expireMethod = param.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
                expireMethod?.Invoke(param, new object[] { true });

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Guid = guid,
                        ParameterType = typeName,
                        Message = "Cleared persistent references"
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"ClearReference failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// Resolve any object identifier (short ID like "C1" or raw GUID string)
        /// to a System.Guid. Returns null if the identifier cannot be resolved.
        /// Short IDs are only valid after a gh_snapshot has populated the registry.
        /// </summary>
        private Guid? ResolveObjectId(string id)
        {
            // Try short-ID registry first (works for C1, G2, etc. AND full GUID strings
            // that happen to be registered — unconditional, no pattern gate)
            var resolved = _idRegistry.Resolve(id);
            if (resolved.HasValue)
                return resolved.Value;

            // Fall back to raw GUID parse
            if (Guid.TryParse(id, out var parsed))
                return parsed;

            return null;
        }

        /// <summary>
        /// Find a document object by any identifier (short ID or GUID string).
        /// Replaces FindObjectByGuid — all callers should use this.
        /// </summary>
        private object? FindObjectById(object document, string id)
        {
            var targetGuid = ResolveObjectId(id);
            if (!targetGuid.HasValue)
                return null;

            var guidString = targetGuid.Value.ToString();
            var objectsProp = document.GetType().GetProperty("Objects");
            var objects = objectsProp?.GetValue(document) as System.Collections.IEnumerable;

            if (objects != null)
            {
                foreach (var obj in objects)
                {
                    var guidProp = obj.GetType().GetProperty("InstanceGuid");
                    var objGuid = guidProp?.GetValue(obj)?.ToString();
                    if (objGuid == guidString)
                        return obj;
                }
            }

            return null;
        }

        /// <summary>
        /// GET /gh/connections?guid=... - Get detailed connection info for a component
        /// Returns sources (what feeds into inputs) and recipients (what outputs feed)
        /// </summary>
        internal ApiResponse GetConnections(string? guid)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_connections");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_connections", null, gh.Error);

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var target = FindObjectById(gh.Document!, guid);
                if (target == null)
                    return new ApiResponse { Success = false, Data = $"Object not found: {guid}" };

                var typeName = target.GetType().Name;
                var name = target.GetType().GetProperty("Name")?.GetValue(target)?.ToString();
                var nickname = target.GetType().GetProperty("NickName")?.GetValue(target)?.ToString();

                var inputConnections = new List<object>();
                var outputConnections = new List<object>();

                // Check if this is a simple param (slider, panel) that can be a source
                var sourcesProp = target.GetType().GetProperty("Sources");
                var recipientsProp = target.GetType().GetProperty("Recipients");

                // Simple params (sliders, panels) have Recipients directly
                if (recipientsProp != null)
                {
                    var recipients = recipientsProp.GetValue(target) as System.Collections.IEnumerable;
                    if (recipients != null)
                    {
                        foreach (var recipient in recipients)
                        {
                            var recipientInfo = GetParamConnectionInfo(recipient, "input");
                            if (recipientInfo != null)
                                outputConnections.Add(recipientInfo);
                        }
                    }
                }

                // Simple params might also have Sources (if wired as input)
                if (sourcesProp != null)
                {
                    var sources = sourcesProp.GetValue(target) as System.Collections.IEnumerable;
                    if (sources != null)
                    {
                        foreach (var source in sources)
                        {
                            var sourceInfo = GetParamConnectionInfo(source, "output");
                            if (sourceInfo != null)
                                inputConnections.Add(sourceInfo);
                        }
                    }
                }

                // Check if this is a component with Params property
                var paramsProp = target.GetType().GetProperty("Params");
                if (paramsProp != null)
                {
                    var paramsServer = paramsProp.GetValue(target);
                    if (paramsServer != null)
                    {
                        var inputProp = paramsServer.GetType().GetProperty("Input");
                        var outputProp = paramsServer.GetType().GetProperty("Output");

                        var inputs = inputProp?.GetValue(paramsServer) as System.Collections.IEnumerable;
                        var outputs = outputProp?.GetValue(paramsServer) as System.Collections.IEnumerable;

                        // Process inputs
                        if (inputs != null)
                        {
                            int idx = 0;
                            foreach (var input in inputs)
                            {
                                var inputName = input.GetType().GetProperty("Name")?.GetValue(input)?.ToString();
                                var inputNickname = input.GetType().GetProperty("NickName")?.GetValue(input)?.ToString();
                                var inputSources = input.GetType().GetProperty("Sources")?.GetValue(input) as System.Collections.IEnumerable;

                                var sourceList = new List<object>();
                                if (inputSources != null)
                                {
                                    foreach (var source in inputSources)
                                    {
                                        var sourceInfo = GetParamConnectionInfo(source, "output");
                                        if (sourceInfo != null)
                                            sourceList.Add(sourceInfo);
                                    }
                                }

                                if (sourceList.Count > 0)
                                {
                                    inputConnections.Add(new
                                    {
                                        ParamIndex = idx,
                                        ParamName = inputName,
                                        ParamNickName = inputNickname,
                                        Sources = sourceList
                                    });
                                }
                                idx++;
                            }
                        }

                        // Process outputs
                        if (outputs != null)
                        {
                            int idx = 0;
                            foreach (var output in outputs)
                            {
                                var outputName = output.GetType().GetProperty("Name")?.GetValue(output)?.ToString();
                                var outputNickname = output.GetType().GetProperty("NickName")?.GetValue(output)?.ToString();
                                var outputRecipients = output.GetType().GetProperty("Recipients")?.GetValue(output) as System.Collections.IEnumerable;

                                var recipientList = new List<object>();
                                if (outputRecipients != null)
                                {
                                    foreach (var recipient in outputRecipients)
                                    {
                                        var recipientInfo = GetParamConnectionInfo(recipient, "input");
                                        if (recipientInfo != null)
                                            recipientList.Add(recipientInfo);
                                    }
                                }

                                if (recipientList.Count > 0)
                                {
                                    outputConnections.Add(new
                                    {
                                        ParamIndex = idx,
                                        ParamName = outputName,
                                        ParamNickName = outputNickname,
                                        Recipients = recipientList
                                    });
                                }
                                idx++;
                            }
                        }
                    }
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Guid = guid,
                        Type = typeName,
                        Name = name,
                        NickName = nickname,
                        Inputs = inputConnections,
                        Outputs = outputConnections
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"GetConnections failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// Helper to get connection info from a param (source or recipient)
        /// </summary>
        private object? GetParamConnectionInfo(object param, string role)
        {
            try
            {
                // Get the owner component of this param
                var attrProp = param.GetType().GetProperty("Attributes");
                var attr = attrProp?.GetValue(param);
                var parentProp = attr?.GetType().GetProperty("Parent");
                var parentAttr = parentProp?.GetValue(attr);

                // Get the owner component from parent attributes
                var ownerProp = parentAttr?.GetType().GetProperty("DocObject");
                var owner = ownerProp?.GetValue(parentAttr);

                // If no parent, the param itself might be the document object (like a slider)
                if (owner == null)
                {
                    var docObjProp = attr?.GetType().GetProperty("DocObject");
                    owner = docObjProp?.GetValue(attr);
                }

                if (owner == null)
                {
                    // Fallback: try to get from param directly
                    owner = param;
                }

                var ownerGuid = owner?.GetType().GetProperty("InstanceGuid")?.GetValue(owner)?.ToString();
                var ownerName = owner?.GetType().GetProperty("Name")?.GetValue(owner)?.ToString();
                var ownerNickname = owner?.GetType().GetProperty("NickName")?.GetValue(owner)?.ToString();
                var ownerType = owner?.GetType().Name;

                var paramName = param.GetType().GetProperty("Name")?.GetValue(param)?.ToString();
                var paramNickname = param.GetType().GetProperty("NickName")?.GetValue(param)?.ToString();

                return new
                {
                    ComponentGuid = ownerGuid,
                    ComponentName = ownerName,
                    ComponentNickName = ownerNickname,
                    ComponentType = ownerType,
                    ParamName = paramName,
                    ParamNickName = paramNickname
                };
            }
            catch
            {
                return null;
            }
        }

        /// <summary>
        /// POST /gh/delete - Delete objects from the canvas
        /// Body: { guids: string[] }
        /// </summary>
        internal ApiResponse DeleteObjects(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_delete");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_delete", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing guids in body" };

            List<string> guidsToDelete;
            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                var guidsEl = args?["guids"];
                guidsToDelete = guidsEl?.EnumerateArray().Select(g => g.GetString()!).ToList() ?? new List<string>();
            }
            catch
            {
                return new ApiResponse { Success = false, Data = "Invalid body format. Expected: { guids: string[] }" };
            }

            if (guidsToDelete.Count == 0)
                return new ApiResponse { Success = false, Data = "No guids provided" };

            try
            {
                // Pre-resolve short IDs and raw GUIDs into a lookup set
                var resolvedGuids = new HashSet<string>();
                foreach (var id in guidsToDelete)
                {
                    var resolved = ResolveObjectId(id);
                    if (resolved.HasValue)
                        resolvedGuids.Add(resolved.Value.ToString());
                }

                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;

                var toRemove = new List<object>();
                if (objects != null)
                {
                    foreach (var obj in objects)
                    {
                        var guidProp = obj.GetType().GetProperty("InstanceGuid");
                        var guid = guidProp?.GetValue(obj)?.ToString();
                        if (guid != null && resolvedGuids.Contains(guid))
                        {
                            toRemove.Add(obj);
                        }
                    }
                }

                // RemoveObject expects IGH_Attributes, not the document object
                var removeMethod = gh.Document.GetType().GetMethods()
                    .Where(m => m.Name == "RemoveObject")
                    .FirstOrDefault(m =>
                    {
                        var parms = m.GetParameters();
                        return parms.Length == 2 && parms[1].ParameterType == typeof(bool);
                    });

                // Record undo BEFORE deletion
                if (toRemove.Count > 0)
                {
                    try
                    {
                        var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                        if (undoUtil != null)
                            RecordUndoEvent(undoUtil, "Rook: delete objects", toRemove, isAdd: false);
                    }
                    catch { /* undo recording is best-effort */ }
                }

                int removed = 0;
                foreach (var obj in toRemove)
                {
                    var attrProp = obj.GetType().GetProperty("Attributes");
                    var attributes = attrProp?.GetValue(obj);
                    if (attributes != null)
                    {
                        removeMethod?.Invoke(gh.Document, new object[] { attributes, true });
                        removed++;
                    }
                }

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Deleted = removed,
                        RequestedGuids = guidsToDelete
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"DeleteObjects failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/preview - Set preview visibility for objects on the canvas
        /// Body: { guids: string[], hidden: bool }
        /// If guids is empty/null, applies to all objects
        /// </summary>
        public ApiResponse SetPreview(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_preview");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_preview", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            List<string>? guids;
            bool hidden;
            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                hidden = args?.ContainsKey("hidden") == true && args["hidden"].GetBoolean();

                if (args?.ContainsKey("guids") == true && args["guids"].ValueKind == JsonValueKind.Array)
                {
                    guids = args["guids"].EnumerateArray()
                        .Where(g => g.ValueKind == JsonValueKind.String)
                        .Select(g => g.GetString()!)
                        .ToList();
                }
                else
                {
                    guids = null; // Apply to all
                }
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid body format: {ex.Message}" };
            }

            try
            {
                // Pre-resolve short IDs and raw GUIDs into a lookup set
                HashSet<string>? resolvedGuids = null;
                if (guids != null && guids.Count > 0)
                {
                    resolvedGuids = new HashSet<string>();
                    foreach (var id in guids)
                    {
                        var resolved = ResolveObjectId(id);
                        if (resolved.HasValue)
                            resolvedGuids.Add(resolved.Value.ToString());
                    }
                }

                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;

                int modified = 0;
                if (objects != null)
                {
                    foreach (var obj in objects)
                    {
                        // Check if we should modify this object
                        if (resolvedGuids != null && resolvedGuids.Count > 0)
                        {
                            var guidProp = obj.GetType().GetProperty("InstanceGuid");
                            var guid = guidProp?.GetValue(obj)?.ToString();
                            if (guid == null || !resolvedGuids.Contains(guid))
                                continue;
                        }

                        // Set Hidden property (controls preview visibility)
                        var hiddenProp = obj.GetType().GetProperty("Hidden");
                        if (hiddenProp != null && hiddenProp.CanWrite)
                        {
                            hiddenProp.SetValue(obj, hidden);
                            modified++;
                        }
                    }
                }

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Modified = modified,
                        Hidden = hidden,
                        TargetGuids = guids,
                        AppliedToAll = guids == null || guids.Count == 0
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"SetPreview failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/move - Move objects to new positions on the canvas
        /// Body: { positions: [{guid: string, x: number, y: number}, ...] }
        /// </summary>
        public ApiResponse MoveObjects(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_move");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_move", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing positions in body" };

            List<(string guid, float x, float y)> positions;
            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                var positionsEl = args?["positions"];
                positions = positionsEl?.EnumerateArray().Select(p => (
                    guid: p.GetProperty("guid").GetString()!,
                    x: (float)p.GetProperty("x").GetDouble(),
                    y: (float)p.GetProperty("y").GetDouble()
                )).ToList() ?? new List<(string, float, float)>();
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid body format. Expected: {{ positions: [{{guid, x, y}}, ...] }}. Error: {ex.Message}" };
            }

            if (positions.Count == 0)
                return new ApiResponse { Success = false, Data = "No positions provided" };

            try
            {
                // Get UndoUtil for recording pivot changes (best-effort)
                object? undoUtil = null;
                try
                {
                    undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                }
                catch { /* undo recording is best-effort */ }

                int moved = 0;
                var results = new List<object>();

                // Phase 1: Resolve all objects to move (needed for batch undo recording)
                var moveTargets = new List<(object obj, object attr, PropertyInfo pivotProp, string guid, float x, float y)>();

                foreach (var pos in positions)
                {
                    var obj = FindObjectById(gh.Document!, pos.guid);
                    if (obj == null)
                    {
                        results.Add(new { guid = pos.guid, success = false, error = "Object not found" });
                        continue;
                    }

                    var attrProp = obj.GetType().GetProperty("Attributes");
                    var attr = attrProp?.GetValue(obj);
                    if (attr == null)
                    {
                        results.Add(new { guid = pos.guid, success = false, error = "No attributes" });
                        continue;
                    }

                    var pivotProp = attr.GetType().GetProperty("Pivot");
                    if (pivotProp == null || !pivotProp.CanWrite)
                    {
                        results.Add(new { guid = pos.guid, success = false, error = "Cannot set Pivot" });
                        continue;
                    }

                    moveTargets.Add((obj, attr, pivotProp, pos.guid, pos.x, pos.y));
                }

                // Phase 2: Record pivot undo BEFORE changing positions
                // RecordPivotEvent snapshots current pivots so Ctrl+Z can restore them.
                if (moveTargets.Count > 0 && undoUtil != null)
                {
                    try
                    {
                        RecordPivotUndoEvent(undoUtil, "Rook: move components",
                            moveTargets.Select(t => t.obj).ToList());
                    }
                    catch { /* undo recording is best-effort */ }
                }

                // Phase 3: Apply new positions
                foreach (var (obj, attr, pivotProp, guid, x, y) in moveTargets)
                {
                    pivotProp.SetValue(attr, new PointF(x, y));

                    // Force layout recalculation after pivot change
                    var expireLayoutMethod = attr.GetType().GetMethod("ExpireLayout");
                    expireLayoutMethod?.Invoke(attr, null);

                    // Also try PerformLayout if available
                    var performLayoutMethod = attr.GetType().GetMethod("PerformLayout");
                    performLayoutMethod?.Invoke(attr, null);

                    moved++;
                    results.Add(new { guid, success = true, x, y });
                }

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Moved = moved,
                        Total = positions.Count,
                        Results = results
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"MoveObjects failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/group - Create a group containing specified objects
        /// Body: { guids: string[], nickname?: string, colour?: string (hex like "#FF5500") }
        /// </summary>
        internal ApiResponse CreateGroup(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_group");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_group", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            List<string> guids;
            string? nickname = null;
            string? colourHex = null;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                var guidsEl = args?["guids"];
                guids = guidsEl?.EnumerateArray().Select(g => g.GetString()!).ToList() ?? new List<string>();
                if (args != null)
                {
                    if (args.TryGetValue("nickname", out var n)) nickname = n.GetString();
                    if (args.TryGetValue("colour", out var c)) colourHex = c.GetString();
                }
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid body format. Expected: {{ guids: string[], nickname?: string, colour?: string }}. Error: {ex.Message}" };
            }

            if (guids.Count == 0)
                return new ApiResponse { Success = false, Data = "No guids provided" };

            try
            {
                // Create GH_Group instance
                var groupType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Group");
                if (groupType == null)
                    return new ApiResponse { Success = false, Data = "GH_Group type not found" };

                var group = Activator.CreateInstance(groupType);
                if (group == null)
                    return new ApiResponse { Success = false, Data = "Failed to create GH_Group instance" };

                // Set nickname if provided
                if (!string.IsNullOrEmpty(nickname))
                {
                    var nicknameProp = group.GetType().GetProperty("NickName");
                    nicknameProp?.SetValue(group, nickname);
                }

                // Set colour if provided
                if (!string.IsNullOrEmpty(colourHex))
                {
                    try
                    {
                        var color = ColorTranslator.FromHtml(colourHex);
                        var colourProp = group.GetType().GetProperty("Colour");
                        colourProp?.SetValue(group, color);
                    }
                    catch { /* ignore invalid color */ }
                }

                // Add objects to group by GUID
                var addObjectMethod = group.GetType().GetMethod("AddObject", new[] { typeof(Guid) });
                int added = 0;
                foreach (var guidStr in guids)
                {
                    if (Guid.TryParse(guidStr, out var guid))
                    {
                        addObjectMethod?.Invoke(group, new object[] { guid });
                        added++;
                    }
                }

                // Create attributes for the group
                var createAttrMethod = group.GetType().GetMethod("CreateAttributes", BindingFlags.Public | BindingFlags.Instance);
                createAttrMethod?.Invoke(group, null);

                // Add to document using the same helper as other components
                var groupGuid = AddObjectToDocument(gh.Document!, group);

                // Record undo for group creation
                try
                {
                    var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                    if (undoUtil != null)
                        RecordUndoEvent(undoUtil, "Rook: create group", new List<object> { group }, isAdd: true);
                }
                catch { /* undo recording is best-effort */ }

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Created = true,
                        Type = "GH_Group",
                        Guid = groupGuid,
                        NickName = nickname,
                        ObjectsAdded = added
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"CreateGroup failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/cluster - Create a cluster from specified objects
        /// Body: { guids: string[], nickname?: string, x?: number, y?: number }
        /// </summary>
        public ApiResponse CreateCluster(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_cluster");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_cluster", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            List<string> guids;
            string? nickname = null;
            float x = 200, y = 200;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                var guidsEl = args?["guids"];
                guids = guidsEl?.EnumerateArray().Select(g => g.GetString()!).ToList() ?? new List<string>();
                if (args != null)
                {
                    if (args.TryGetValue("nickname", out var n)) nickname = n.GetString();
                    if (args.TryGetValue("x", out var xEl)) x = xEl.GetSingle();
                    if (args.TryGetValue("y", out var yEl)) y = yEl.GetSingle();
                }
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid body format. Error: {ex.Message}" };
            }

            if (guids.Count == 0)
                return new ApiResponse { Success = false, Data = "No guids provided" };

            try
            {
                // Get cluster type
                var clusterType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Cluster");
                if (clusterType == null)
                    return new ApiResponse { Success = false, Data = "GH_Cluster type not found" };

                // Collect objects to cluster
                var objectsToCluster = new List<object>();
                foreach (var guidStr in guids)
                {
                    var obj = FindObjectById(gh.Document!, guidStr);
                    if (obj != null)
                        objectsToCluster.Add(obj);
                }

                if (objectsToCluster.Count == 0)
                    return new ApiResponse { Success = false, Data = "No valid objects found for clustering" };

                // Create empty cluster
                var cluster = Activator.CreateInstance(clusterType);
                if (cluster == null)
                    return new ApiResponse { Success = false, Data = "Failed to create GH_Cluster instance" };

                // Set nickname
                if (!string.IsNullOrEmpty(nickname))
                {
                    var nicknameProp = cluster.GetType().GetProperty("NickName");
                    nicknameProp?.SetValue(cluster, nickname);
                }

                // Set Attributes.Selected = true on each object to cluster
                // SelectedObjects() iterates document objects and checks Attributes.Selected
                foreach (var obj in objectsToCluster)
                {
                    var attrProp = obj.GetType().GetProperty("Attributes");
                    var attr = attrProp?.GetValue(obj);
                    if (attr != null)
                    {
                        var selectedProp = attr.GetType().GetProperty("Selected");
                        selectedProp?.SetValue(attr, true);
                    }
                }

                // Call CreateFromSelection - encapsulates selected objects into cluster
                var createFromSelectionMethod = clusterType.GetMethod("CreateFromSelection");
                if (createFromSelectionMethod == null)
                    return new ApiResponse { Success = false, Data = "CreateFromSelection method not found" };

                // CreateFromSelection(document, deleteOriginals=true, reconnectSources=true, reconnectRecipients=true)
                createFromSelectionMethod.Invoke(cluster, new object[] { gh.Document!, true, true, true });

                // Deselect all after clustering
                var deselectAllMethod = gh.Document!.GetType().GetMethod("DeselectAll");
                deselectAllMethod?.Invoke(gh.Document, null);

                // Step 3: Set position and add to document
                var createAttrMethod = clusterType.GetMethod("CreateAttributes", BindingFlags.Public | BindingFlags.Instance);
                createAttrMethod?.Invoke(cluster, null);

                var clusterAttrProp = clusterType.GetProperty("Attributes");
                if (clusterAttrProp != null)
                {
                    var attr = clusterAttrProp.GetValue(cluster);
                    var pivotProp = attr?.GetType().GetProperty("Pivot");
                    pivotProp?.SetValue(attr, new PointF(x, y));
                }

                var clusterGuid = AddObjectToDocument(gh.Document, cluster);
                RefreshCanvas(gh.Canvas!);

                // Get cluster info
                var paramsProp = clusterType.GetProperty("Params");
                var inputCount = 0;
                var outputCount = 0;
                if (paramsProp != null)
                {
                    var paramsObj = paramsProp.GetValue(cluster);
                    var inputProp = paramsObj?.GetType().GetProperty("Input");
                    var outputProp = paramsObj?.GetType().GetProperty("Output");
                    var inputs = inputProp?.GetValue(paramsObj) as System.Collections.IList;
                    var outputs = outputProp?.GetValue(paramsObj) as System.Collections.IList;
                    inputCount = inputs?.Count ?? 0;
                    outputCount = outputs?.Count ?? 0;
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Created = true,
                        Type = "GH_Cluster",
                        Guid = clusterGuid,
                        NickName = nickname,
                        ObjectsClustered = objectsToCluster.Count,
                        InputCount = inputCount,
                        OutputCount = outputCount
                    }
                };
            }
            catch (Exception ex)
            {
                var innerMsg = ex.InnerException?.Message ?? "";
                return new ApiResponse
                {
                    Success = false,
                    Data = new
                    {
                        Error = "CreateCluster failed",
                        Message = ex.Message,
                        InnerMessage = innerMsg
                    }
                };
            }
        }

        /// <summary>
        /// POST /gh/clear - Clear all objects from the canvas
        /// </summary>
        public ApiResponse ClearCanvas()
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_clear");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_clear", null, gh.Error);

            try
            {
                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;

                var allObjects = objects?.Cast<object>().ToList() ?? new List<object>();
                var count = allObjects.Count;

                // RemoveObject expects IGH_Attributes, not the document object
                // Find overload: RemoveObject(IGH_Attributes, bool)
                var removeMethod = gh.Document.GetType().GetMethods()
                    .Where(m => m.Name == "RemoveObject")
                    .FirstOrDefault(m =>
                    {
                        var parms = m.GetParameters();
                        return parms.Length == 2 && parms[1].ParameterType == typeof(bool);
                    });

                foreach (var obj in allObjects)
                {
                    // Get the Attributes property from the document object
                    var attrProp = obj.GetType().GetProperty("Attributes");
                    var attributes = attrProp?.GetValue(obj);
                    if (attributes != null)
                    {
                        removeMethod?.Invoke(gh.Document, new object[] { attributes, false });
                    }
                }

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Cleared = true,
                        ObjectsRemoved = count
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"ClearCanvas failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/undo - Undo the last operation on the GH canvas.
        /// Calls GH_Document.Undo() which reverses the most recent undo event.
        /// Each gh_edit batch and individual GH operation records undo events.
        /// </summary>
        public ApiResponse UndoCanvas()
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_undo");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_undo", null, gh.Error);

            try
            {
                var undoMethod = gh.Document!.GetType().GetMethod("Undo",
                    BindingFlags.Public | BindingFlags.Instance,
                    null, Type.EmptyTypes, null);

                if (undoMethod == null)
                    return new ApiResponse { Success = false, Data = "GH_Document.Undo() method not found" };

                var result = undoMethod.Invoke(gh.Document, null);
                var success = result is bool b && b;

                RefreshCanvas(gh.Canvas!);

                // TakeSnapshot rebuilds ShortIdRegistry (incrementing epoch),
                // so the caller gets correct IDs for the post-undo canvas state.
                var snapshot = success ? TakeSnapshot(null) : null;

                return new ApiResponse
                {
                    Success = success,
                    Data = success
                        ? new { message = "Undo successful", epoch = _idRegistry.Epoch, snapshot = snapshot?.Data }
                        : (object)"Nothing to undo"
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"Undo failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// Record an undo event via GH_Document.UndoUtil for a batch of objects.
        /// Uses RecordAddObjectEvent for creates and RecordRemoveObjectEvent for deletes.
        /// Best-effort: callers should catch exceptions.
        /// </summary>
        private void RecordUndoEvent(object undoUtil, string name, List<object> objects, bool isAdd)
        {
            if (objects.Count == 0) return;

            // UndoUtil.RecordAddObjectEvent(string, IEnumerable<IGH_DocumentObject>)
            // UndoUtil.RecordRemoveObjectEvent(string, IEnumerable<IGH_DocumentObject>)
            var methodName = isAdd ? "RecordAddObjectEvent" : "RecordRemoveObjectEvent";

            // Find the method that takes (string, IEnumerable<IGH_DocumentObject>)
            var methods = undoUtil.GetType().GetMethods()
                .Where(m => m.Name == methodName && m.GetParameters().Length == 2)
                .ToList();

            var method = methods.FirstOrDefault(m =>
            {
                var p = m.GetParameters();
                return p[0].ParameterType == typeof(string) &&
                       p[1].ParameterType.IsGenericType;
            }) ?? methods.FirstOrDefault();

            if (method == null) return;

            // Build a List<IGH_DocumentObject> from our objects via reflection.
            // The parameter type is IEnumerable<IGH_DocumentObject>.
            var paramType = method.GetParameters()[1].ParameterType;

            // Get the IGH_DocumentObject element type from the generic parameter
            Type? elementType = null;
            if (paramType.IsGenericType)
            {
                elementType = paramType.GetGenericArguments().FirstOrDefault();
            }

            if (elementType != null)
            {
                // Create List<IGH_DocumentObject>
                var listType = typeof(List<>).MakeGenericType(elementType);
                var list = Activator.CreateInstance(listType) as System.Collections.IList;
                if (list != null)
                {
                    foreach (var obj in objects)
                    {
                        if (elementType.IsAssignableFrom(obj.GetType()))
                            list.Add(obj);
                    }
                    if (list.Count > 0)
                        method.Invoke(undoUtil, new object[] { name, list });
                }
            }
        }

        /// <summary>
        /// Record a wire undo event via GH_Document.UndoUtil for a batch of params.
        /// Uses RecordWireEvent(string, IEnumerable&lt;IGH_Param&gt;) to snapshot
        /// current wire state. Must be called BEFORE wires are changed.
        /// Best-effort: callers should catch exceptions.
        /// </summary>
        private void RecordWireUndoEvent(object undoUtil, string name, List<object> parameters)
        {
            if (parameters.Count == 0) return;

            // UndoUtil.RecordWireEvent(string, IEnumerable<IGH_Param>)
            var methods = undoUtil.GetType().GetMethods()
                .Where(m => m.Name == "RecordWireEvent" && m.GetParameters().Length == 2)
                .ToList();

            var method = methods.FirstOrDefault(m =>
            {
                var p = m.GetParameters();
                return p[0].ParameterType == typeof(string) &&
                       p[1].ParameterType.IsGenericType;
            }) ?? methods.FirstOrDefault();

            if (method == null) return;

            var paramType = method.GetParameters()[1].ParameterType;
            Type? elementType = null;
            if (paramType.IsGenericType)
                elementType = paramType.GetGenericArguments().FirstOrDefault();

            if (elementType != null)
            {
                var listType = typeof(List<>).MakeGenericType(elementType);
                var list = Activator.CreateInstance(listType) as System.Collections.IList;
                if (list != null)
                {
                    foreach (var param in parameters)
                    {
                        if (elementType.IsAssignableFrom(param.GetType()))
                            list.Add(param);
                    }
                    if (list.Count > 0)
                        method.Invoke(undoUtil, new object[] { name, list });
                }
            }
        }

        /// <summary>
        /// Record a generic object-changed undo event via GH_Document.UndoUtil.
        /// Uses RecordGenericObjectEvent(string, IGH_DocumentObject) to snapshot
        /// the full object state. Must be called BEFORE the object is changed.
        /// Best-effort: callers should catch exceptions.
        /// </summary>
        private void RecordGenericObjectUndoEvent(object undoUtil, string name, object documentObject)
        {
            // UndoUtil.RecordGenericObjectEvent(string, IGH_DocumentObject)
            var methods = undoUtil.GetType().GetMethods()
                .Where(m => m.Name == "RecordGenericObjectEvent" && m.GetParameters().Length == 2)
                .ToList();

            var method = methods.FirstOrDefault(m =>
            {
                var p = m.GetParameters();
                return p[0].ParameterType == typeof(string);
            }) ?? methods.FirstOrDefault();

            method?.Invoke(undoUtil, new object[] { name, documentObject });
        }

        /// <summary>
        /// Record a layout undo event via GH_Document.UndoUtil.
        /// Uses RecordLayoutEvent(string, IGH_DocumentObject) to snapshot
        /// current bounds/layout. Must be called BEFORE bounds are changed.
        /// Best-effort: callers should catch exceptions.
        /// </summary>
        private void RecordLayoutUndoEvent(object undoUtil, string name, object documentObject)
        {
            // UndoUtil.RecordLayoutEvent(string, IGH_DocumentObject)
            // Must select the single-object overload, NOT the IEnumerable<IGH_DocumentObject> batch overload.
            var methods = undoUtil.GetType().GetMethods()
                .Where(m => m.Name == "RecordLayoutEvent" && m.GetParameters().Length == 2)
                .ToList();

            var method = methods.FirstOrDefault(m =>
            {
                var p = m.GetParameters();
                return p[0].ParameterType == typeof(string) && !p[1].ParameterType.IsGenericType;
            }) ?? methods.FirstOrDefault(m =>
            {
                var p = m.GetParameters();
                return p[0].ParameterType == typeof(string);
            });

            method?.Invoke(undoUtil, new object[] { name, documentObject });
        }

        /// <summary>
        /// Record a pivot undo event via GH_Document.UndoUtil for a batch of objects.
        /// Uses RecordPivotEvent(string, IEnumerable&lt;IGH_DocumentObject&gt;) to snapshot
        /// current pivot positions. Must be called BEFORE pivots are changed.
        /// Best-effort: callers should catch exceptions.
        /// </summary>
        private void RecordPivotUndoEvent(object undoUtil, string name, List<object> objects)
        {
            if (objects.Count == 0) return;

            // UndoUtil.RecordPivotEvent(string, IEnumerable<IGH_DocumentObject>)
            var methods = undoUtil.GetType().GetMethods()
                .Where(m => m.Name == "RecordPivotEvent" && m.GetParameters().Length == 2)
                .ToList();

            var method = methods.FirstOrDefault(m =>
            {
                var p = m.GetParameters();
                return p[0].ParameterType == typeof(string) &&
                       p[1].ParameterType.IsGenericType;
            }) ?? methods.FirstOrDefault();

            if (method == null) return;

            // Build a List<IGH_DocumentObject> from our objects via reflection.
            var paramType = method.GetParameters()[1].ParameterType;

            Type? elementType = null;
            if (paramType.IsGenericType)
            {
                elementType = paramType.GetGenericArguments().FirstOrDefault();
            }

            if (elementType != null)
            {
                var listType = typeof(List<>).MakeGenericType(elementType);
                var list = Activator.CreateInstance(listType) as System.Collections.IList;
                if (list != null)
                {
                    foreach (var obj in objects)
                    {
                        if (elementType.IsAssignableFrom(obj.GetType()))
                            list.Add(obj);
                    }
                    if (list.Count > 0)
                        method.Invoke(undoUtil, new object[] { name, list });
                }
            }
        }

        /// <summary>
        /// POST /gh/document/open - Open a GH or GHX file
        /// Body: { path: string }
        /// </summary>
        internal static GhOpenDocumentPreflightResult PreflightOpenDocument(string? body)
        {
            if (string.IsNullOrWhiteSpace(body))
            {
                return new GhOpenDocumentPreflightResult
                {
                    Success = false,
                    ErrorCode = "gh_open_request_body_required",
                };
            }

            try
            {
                var json = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (json == null || !json.TryGetValue("path", out var pathElement))
                {
                    return new GhOpenDocumentPreflightResult
                    {
                        Success = false,
                        ErrorCode = "gh_open_path_missing",
                    };
                }

                if (pathElement.ValueKind != JsonValueKind.String)
                {
                    return new GhOpenDocumentPreflightResult
                    {
                        Success = false,
                        ErrorCode = "gh_open_path_invalid",
                    };
                }

                var path = pathElement.GetString();
                if (string.IsNullOrWhiteSpace(path))
                {
                    return new GhOpenDocumentPreflightResult
                    {
                        Success = false,
                        ErrorCode = "gh_open_path_empty",
                    };
                }

                if (!File.Exists(path))
                {
                    return new GhOpenDocumentPreflightResult
                    {
                        Success = false,
                        ErrorCode = "gh_open_file_not_found",
                    };
                }

                return new GhOpenDocumentPreflightResult
                {
                    Success = true,
                    Path = path,
                };
            }
            catch
            {
                return new GhOpenDocumentPreflightResult
                {
                    Success = false,
                    ErrorCode = "gh_open_request_invalid",
                };
            }
        }

        public ApiResponse OpenDocument(string? body)
        {
            var preflight = PreflightOpenDocument(body);
            if (!preflight.Success)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = preflight.ErrorCode,
                };
            }

            var gh = GetGrasshopper(requireDocument: false);
            if (!gh.Success)
                return new ApiResponse { Success = false, Data = gh.Error };

            var lifecycle = new GhDocumentLifecycle();
            var lifecycleResult = lifecycle.Open(preflight.Path!);
            if (!lifecycleResult.Committed)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new
                    {
                        error = GhDocumentLifecycleWire.Code(lifecycleResult.Code),
                        document_registered = lifecycleResult.DocumentRegistered,
                        document_active = lifecycleResult.DocumentActive,
                        rollback_attempted = lifecycleResult.RollbackAttempted,
                        rollback_incomplete = lifecycleResult.RollbackIncomplete,
                    },
                };
            }

            var newDocument = lifecycleResult.Document!;
            var capturedCanvas = lifecycleResult.CapturedCanvas!;
            try
            {
                EnsureReadinessSession(newDocument, capturedCanvas);
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ReadinessAttachmentFailed);
            }

            try
            {
                _idRegistry.Clear();
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.IdRegistryResetFailed);
            }

            try
            {
                RefreshCanvas(capturedCanvas, scheduleSolution: false);
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.CanvasRefreshFailed);
            }

            int? ObjectCount = null;
            try
            {
                var objectsProp = newDocument.GetType().GetProperty("Objects");
                if (objectsProp == null)
                {
                    lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ObjectCountFailed);
                }
                else if (objectsProp.GetValue(newDocument) is System.Collections.IEnumerable objects)
                {
                    ObjectCount = objects.Cast<object>().Count();
                }
                else
                {
                    lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ObjectCountFailed);
                }
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ObjectCountFailed);
            }

            string[] lifecycleWarnings;
            try
            {
                lifecycleWarnings = lifecycleResult.Warnings
                    .Select(GhDocumentLifecycleWire.Warning)
                    .ToArray();
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.TelemetryProjectionFailed);
                lifecycleWarnings = new[] { "telemetry_projection_failed" };
            }

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    Opened = true,
                    Path = preflight.Path,
                    FileName = System.IO.Path.GetFileName(preflight.Path),
                    ObjectCount,
                    DocumentRegistered = lifecycleResult.DocumentRegistered,
                    DocumentActive = lifecycleResult.DocumentActive,
                    RegistrationIndex = lifecycleResult.RegistrationIndex,
                    existingDocumentReused = lifecycleResult.PathAlreadyRegistered,
                    Warnings = lifecycleWarnings,
                },
            };
        }

        /// <summary>
        /// POST /gh/document/new - Create a new empty GH document
        /// </summary>
        public ApiResponse NewDocument()
        {
            var gh = GetGrasshopper(requireDocument: false);
            if (!gh.Success)
                return new ApiResponse { Success = false, Data = gh.Error };

            var lifecycle = new GhDocumentLifecycle();
            var lifecycleResult = lifecycle.CreateNew();
            if (!lifecycleResult.Committed)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new
                    {
                        error = GhDocumentLifecycleWire.Code(lifecycleResult.Code),
                        document_registered = lifecycleResult.DocumentRegistered,
                        document_active = lifecycleResult.DocumentActive,
                        rollback_attempted = lifecycleResult.RollbackAttempted,
                        rollback_incomplete = lifecycleResult.RollbackIncomplete,
                    },
                };
            }

            var newDocument = lifecycleResult.Document!;
            var capturedCanvas = lifecycleResult.CapturedCanvas!;
            try
            {
                EnsureReadinessSession(newDocument, capturedCanvas);
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ReadinessAttachmentFailed);
            }

            try
            {
                _idRegistry.Clear();
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.IdRegistryResetFailed);
            }

            try
            {
                RefreshCanvas(capturedCanvas, scheduleSolution: false);
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.CanvasRefreshFailed);
            }

            int? ObjectCount = null;
            try
            {
                var objectsProp = newDocument.GetType().GetProperty("Objects");
                if (objectsProp == null)
                {
                    lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ObjectCountFailed);
                }
                else if (objectsProp.GetValue(newDocument) is System.Collections.IEnumerable objects)
                {
                    ObjectCount = objects.Cast<object>().Count();
                }
                else
                {
                    lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ObjectCountFailed);
                }
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.ObjectCountFailed);
            }

            string[] lifecycleWarnings;
            try
            {
                lifecycleWarnings = lifecycleResult.Warnings
                    .Select(GhDocumentLifecycleWire.Warning)
                    .ToArray();
            }
            catch
            {
                lifecycleResult.AddWarning(GhDocumentLifecycleWarning.TelemetryProjectionFailed);
                lifecycleWarnings = new[] { "telemetry_projection_failed" };
            }

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    Created = true,
                    Message = "New empty document created",
                    ObjectCount,
                    DocumentRegistered = lifecycleResult.DocumentRegistered,
                    DocumentActive = lifecycleResult.DocumentActive,
                    RegistrationIndex = lifecycleResult.RegistrationIndex,
                    Warnings = lifecycleWarnings,
                },
            };
        }

        /// <summary>
        /// POST /gh/explore-selection - Investigate selection mechanisms
        /// Body: { guids: string[] }
        /// </summary>
        public ApiResponse ExploreSelection(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_explore_selection");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_explore_selection", null, gh.Error);

            List<string> guids = new List<string>();
            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    var guidsEl = args?["guids"];
                    guids = guidsEl?.EnumerateArray().Select(g => g.GetString()!).ToList() ?? new List<string>();
                }
                catch { }
            }

            var exploration = new Dictionary<string, object>();

            try
            {
                // ===== CANVAS EXPLORATION =====
                var canvasType = gh.Canvas!.GetType();

                // Get hit-testing and find methods on canvas
                var canvasFindMethods = canvasType.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.NonPublic)
                    .Where(m => m.Name.Contains("Find") || m.Name.Contains("Hit") || m.Name.Contains("At") || m.Name.Contains("Query"))
                    .Select(m => $"{(m.IsPublic ? "public" : "nonpublic")} {m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))})")
                    .Distinct()
                    .ToList();
                exploration["canvasFindMethods"] = canvasFindMethods;

                // Get all selection-related properties on canvas
                var canvasSelectionProps = canvasType.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                    .Where(p => p.Name.Contains("Select") || p.Name.Contains("select"))
                    .Select(p => $"{p.Name}:{p.PropertyType.Name}")
                    .ToList();
                exploration["canvasSelectionProps"] = canvasSelectionProps;

                // Get all selection-related methods on canvas
                var canvasSelectionMethods = canvasType.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                    .Where(m => m.Name.Contains("Select") || m.Name.Contains("select"))
                    .Select(m => $"{m.Name}({string.Join(", ", m.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))})")
                    .Distinct()
                    .ToList();
                exploration["canvasSelectionMethods"] = canvasSelectionMethods;

                // ===== DOCUMENT EXPLORATION =====
                var docType = gh.Document!.GetType();

                // Get all selection-related methods on document (full detail)
                var docSelectionMethods = docType.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                    .Where(m => m.Name.Contains("Select") || m.Name.Contains("select"))
                    .Select(m => $"{m.Name}({string.Join(", ", m.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))})")
                    .Distinct()
                    .ToList();
                exploration["documentSelectionMethods"] = docSelectionMethods;

                // ===== GH_RelevantObjectData EXPLORATION =====
                var relevantDataType = gh.Assembly!.GetType("Grasshopper.Kernel.GH_RelevantObjectData");
                if (relevantDataType != null)
                {
                    // Constructors (include non-public)
                    var ctors = relevantDataType.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                        .Select(c => $"{(c.IsPublic ? "public" : "nonpublic")} ctor({string.Join(", ", c.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))})")
                        .ToList();
                    exploration["GH_RelevantObjectData_Constructors"] = ctors;

                    // All methods with RETURN TYPES
                    var methods = relevantDataType.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                        .Select(m => $"{m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name))})")
                        .ToList();
                    exploration["GH_RelevantObjectData_Methods"] = methods;

                    // Non-public methods too
                    var nonPublicMethods = relevantDataType.GetMethods(BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                        .Select(m => $"{m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name))})")
                        .ToList();
                    exploration["GH_RelevantObjectData_NonPublicMethods"] = nonPublicMethods;

                    // All properties
                    var props = relevantDataType.GetProperties()
                        .Select(p => $"{p.Name}:{p.PropertyType.Name}(get:{p.CanRead},set:{p.CanWrite})")
                        .ToList();
                    exploration["GH_RelevantObjectData_Properties"] = props;

                    // Static methods (maybe there's a factory?)
                    var staticMethods = relevantDataType.GetMethods(BindingFlags.Public | BindingFlags.Static)
                        .Select(m => $"{m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name))})")
                        .ToList();
                    exploration["GH_RelevantObjectData_StaticMethods"] = staticMethods;

                    // Fields (writable)
                    var fields = relevantDataType.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                        .Select(f => $"{(f.IsPublic ? "public" : "nonpublic")} {f.FieldType.Name} {f.Name}")
                        .ToList();
                    exploration["GH_RelevantObjectData_Fields"] = fields;
                }

                // ===== TRY ACTUAL SELECTION =====
                if (guids.Count > 0)
                {
                    var obj = FindObjectById(gh.Document, guids[0]);
                    if (obj != null)
                    {
                        exploration["testObjectType"] = obj.GetType().Name;

                        // Get attributes
                        var attrProp = obj.GetType().GetProperty("Attributes");
                        var attr = attrProp?.GetValue(obj);

                        if (attr != null)
                        {
                            // Check Selected property
                            var selectedProp = attr.GetType().GetProperty("Selected");
                            var beforeSelected = selectedProp?.GetValue(attr);
                            exploration["beforeSelected"] = beforeSelected;

                            // Get pivot
                            var pivotProp = attr.GetType().GetProperty("Pivot");
                            var pivot = pivotProp?.GetValue(attr);
                            exploration["pivot"] = pivot?.ToString();

                            // Get Bounds
                            var boundsProp = attr.GetType().GetProperty("Bounds");
                            var bounds = boundsProp?.GetValue(attr);
                            exploration["bounds"] = bounds?.ToString();

                            // Try setting Selected = true
                            selectedProp?.SetValue(attr, true);
                            var afterSelectedAttr = selectedProp?.GetValue(attr);
                            exploration["afterSelectedOnAttr"] = afterSelectedAttr;

                            // Check document selection
                            var selectedObjsProp = gh.Document.GetType().GetProperty("SelectedObjects");
                            var selectedObjs = selectedObjsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;
                            var docSelCount = selectedObjs?.Cast<object>().Count() ?? 0;
                            exploration["docSelectedCountAfterAttrSet"] = docSelCount;

                            // Try using GH_RelevantObjectData with PointF
                            if (relevantDataType != null && pivot is PointF pf)
                            {
                                try
                                {
                                    // First deselect to test fresh
                                    selectedProp?.SetValue(attr, false);
                                    var deselectAllMethod = gh.Document.GetType().GetMethod("DeselectAll");
                                    deselectAllMethod?.Invoke(gh.Document, null);

                                    // APPROACH 1: Create GH_RelevantObjectData with point and set internal field
                                    var relevantData = Activator.CreateInstance(relevantDataType, new object[] { pf });
                                    exploration["approach1_relevantDataCreated"] = relevantData != null;

                                    // Try setting m_obj field directly
                                    var objField = relevantDataType.GetField("m_obj", BindingFlags.NonPublic | BindingFlags.Instance);
                                    if (objField != null && relevantData != null)
                                    {
                                        objField.SetValue(relevantData, obj);
                                        exploration["approach1_fieldSet"] = true;

                                        // Check if it stuck
                                        var rdObjProp = relevantDataType.GetProperty("Object");
                                        var rdObj = rdObjProp?.GetValue(relevantData);
                                        exploration["approach1_objectAfterSet"] = rdObj != null ? rdObj.GetType().Name : "null";
                                        exploration["approach1_objectMatches"] = rdObj == obj;

                                        // Now try Select
                                        var selectMethod = gh.Document.GetType().GetMethod("Select", new[] { relevantDataType });
                                        selectMethod?.Invoke(gh.Document, new object[] { relevantData });

                                        selectedObjs = selectedObjsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;
                                        docSelCount = selectedObjs?.Cast<object>().Count() ?? 0;
                                        exploration["approach1_docSelectedCount"] = docSelCount;
                                    }
                                    else
                                    {
                                        exploration["approach1_fieldNotFound"] = true;
                                    }

                                    // APPROACH 2: Try CreateObjectData instance method
                                    var createObjDataMethod = relevantDataType.GetMethod("CreateObjectData",
                                        BindingFlags.Public | BindingFlags.Instance);
                                    if (createObjDataMethod != null)
                                    {
                                        exploration["approach2_methodFound"] = true;
                                        exploration["approach2_returnType"] = createObjDataMethod.ReturnType.Name;

                                        // Call CreateObjectData on a fresh instance
                                        var tempInstance = Activator.CreateInstance(relevantDataType, new object[] { new PointF(0, 0) });
                                        var createdData = createObjDataMethod.Invoke(tempInstance, new object[] { obj });
                                        exploration["approach2_createdDataType"] = createdData?.GetType().Name ?? "null";

                                        if (createdData != null)
                                        {
                                            // Check what's inside it
                                            var rdObjProp = relevantDataType.GetProperty("Object");
                                            var rdObj = rdObjProp?.GetValue(createdData);
                                            exploration["approach2_objectInside"] = rdObj != null ? rdObj.GetType().Name : "null";

                                            // Deselect and try with this
                                            deselectAllMethod?.Invoke(gh.Document, null);
                                            var selectMethod = gh.Document.GetType().GetMethod("Select", new[] { relevantDataType });
                                            selectMethod?.Invoke(gh.Document, new object[] { createdData });

                                            selectedObjs = selectedObjsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;
                                            docSelCount = selectedObjs?.Cast<object>().Count() ?? 0;
                                            exploration["approach2_docSelectedCount"] = docSelCount;
                                        }
                                    }

                                    // APPROACH 3: Try SelectAll()
                                    deselectAllMethod?.Invoke(gh.Document, null);
                                    var selectAllMethod = gh.Document.GetType().GetMethod("SelectAll");
                                    selectAllMethod?.Invoke(gh.Document, null);

                                    selectedObjs = selectedObjsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;
                                    docSelCount = selectedObjs?.Cast<object>().Count() ?? 0;
                                    exploration["approach3_selectAllCount"] = docSelCount;

                                    // Check if object's attribute shows selected
                                    var objAttrAfterSelectAll = selectedProp?.GetValue(attr);
                                    exploration["approach3_attrSelectedAfterSelectAll"] = objAttrAfterSelectAll;
                                }
                                catch (Exception ex)
                                {
                                    exploration["relevantDataError"] = ex.InnerException?.Message ?? ex.Message;
                                    exploration["relevantDataErrorStack"] = ex.InnerException?.StackTrace?.Split('\n').Take(3).ToArray();
                                }
                            }
                        }
                    }
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = exploration
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new { Error = ex.Message, Exploration = exploration }
                };
            }
        }

        /// <summary>
        /// POST /gh/explore-cluster - Investigate GH_Cluster class for alternative creation methods
        /// </summary>
        public ApiResponse ExploreCluster(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_explore_cluster");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_explore_cluster", null, gh.Error);

            var exploration = new Dictionary<string, object>();

            try
            {
                var clusterType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Cluster");
                if (clusterType == null)
                    return new ApiResponse { Success = false, Data = "GH_Cluster type not found" };

                // All public methods
                var publicMethods = clusterType.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                    .Select(m => $"{m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))})")
                    .OrderBy(s => s)
                    .ToList();
                exploration["publicMethods"] = publicMethods;

                // Static methods
                var staticMethods = clusterType.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
                    .Select(m => $"{m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))})")
                    .ToList();
                exploration["staticMethods"] = staticMethods;

                // Properties
                var properties = clusterType.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                    .Select(p => $"{p.PropertyType.Name} {p.Name}(get:{p.CanRead},set:{p.CanWrite})")
                    .ToList();
                exploration["properties"] = properties;

                // Methods related to "Create" or "Add" or "Document"
                var createMethods = clusterType.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                    .Where(m => m.Name.Contains("Create") || m.Name.Contains("Add") || m.Name.Contains("Document") || m.Name.Contains("Object"))
                    .Select(m => $"{(m.IsPublic ? "public" : "nonpublic")} {(m.IsStatic ? "static " : "")}{m.ReturnType.Name} {m.Name}({string.Join(", ", m.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))})")
                    .Distinct()
                    .ToList();
                exploration["createAddDocumentMethods"] = createMethods;

                // Fields
                var fields = clusterType.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                    .Select(f => $"{(f.IsPublic ? "public" : "nonpublic")} {f.FieldType.Name} {f.Name}")
                    .ToList();
                exploration["fields"] = fields;

                // Check for ClusterDocument property or similar
                var docRelated = clusterType.GetMembers(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                    .Where(m => m.Name.ToLower().Contains("doc"))
                    .Select(m => $"{m.MemberType}: {m.Name}")
                    .ToList();
                exploration["docRelatedMembers"] = docRelated;

                // Check inheritance
                var baseType = clusterType.BaseType;
                var inheritance = new List<string>();
                while (baseType != null && baseType != typeof(object))
                {
                    inheritance.Add(baseType.Name);
                    baseType = baseType.BaseType;
                }
                exploration["inheritance"] = inheritance;

                // Interfaces
                var interfaces = clusterType.GetInterfaces()
                    .Select(i => i.Name)
                    .ToList();
                exploration["interfaces"] = interfaces;

                return new ApiResponse
                {
                    Success = true,
                    Data = exploration
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new { Error = ex.Message, Exploration = exploration }
                };
            }
        }

        /// <summary>
        /// GET /gh/groups - Query all GH_Group objects on canvas with member GUIDs, nickname, colour, bounds
        /// </summary>
        public ApiResponse GetGroups()
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_groups");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_groups", null, gh.Error);

            try
            {
                var groupType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Group");
                if (groupType == null)
                    return new ApiResponse { Success = false, Data = "GH_Group type not found" };

                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;
                if (objects == null)
                    return new ApiResponse { Success = true, Data = new { Groups = new List<object>() } };

                var groups = new List<object>();
                foreach (var obj in objects)
                {
                    if (!groupType.IsInstanceOfType(obj))
                        continue;

                    var guidProp = obj.GetType().GetProperty("InstanceGuid");
                    var guid = guidProp?.GetValue(obj)?.ToString();

                    var nicknameProp = obj.GetType().GetProperty("NickName");
                    var nickname = nicknameProp?.GetValue(obj)?.ToString();

                    // Get colour
                    string? colourHex = null;
                    var colourProp = obj.GetType().GetProperty("Colour");
                    if (colourProp != null)
                    {
                        var colour = colourProp.GetValue(obj);
                        if (colour is Color c)
                            colourHex = c.A < 255
                                ? $"#{c.R:X2}{c.G:X2}{c.B:X2}{c.A:X2}"
                                : $"#{c.R:X2}{c.G:X2}{c.B:X2}";
                    }

                    // Get member GUIDs via ObjectIDs property
                    var memberGuids = new List<string>();
                    var objectIdsProp = obj.GetType().GetMethod("ObjectIDs");
                    if (objectIdsProp != null)
                    {
                        var ids = objectIdsProp.Invoke(obj, null) as System.Collections.IEnumerable;
                        if (ids != null)
                        {
                            foreach (var id in ids)
                                memberGuids.Add(id.ToString()!);
                        }
                    }
                    else
                    {
                        // Fallback: try ObjectCount + Objects()
                        var objectsMethod = obj.GetType().GetMethod("Objects");
                        if (objectsMethod != null)
                        {
                            var memberObjects = objectsMethod.Invoke(obj, null) as System.Collections.IEnumerable;
                            if (memberObjects != null)
                            {
                                foreach (var member in memberObjects)
                                {
                                    var memberGuidProp = member.GetType().GetProperty("InstanceGuid");
                                    if (memberGuidProp != null)
                                        memberGuids.Add(memberGuidProp.GetValue(member)?.ToString()!);
                                }
                            }
                        }
                    }

                    // Get bounds from Attributes
                    float? x = null, y = null, width = null, height = null;
                    var attrProp = obj.GetType().GetProperty("Attributes");
                    if (attrProp != null)
                    {
                        var attr = attrProp.GetValue(obj);
                        if (attr != null)
                        {
                            var boundsProp = attr.GetType().GetProperty("Bounds");
                            if (boundsProp != null)
                            {
                                var bounds = boundsProp.GetValue(attr);
                                if (bounds is RectangleF rf)
                                {
                                    x = rf.X;
                                    y = rf.Y;
                                    width = rf.Width;
                                    height = rf.Height;
                                }
                            }
                        }
                    }

                    groups.Add(new
                    {
                        Guid = guid,
                        NickName = nickname,
                        Colour = colourHex,
                        Members = memberGuids,
                        Bounds = x.HasValue ? new { X = x.Value, Y = y!.Value, Width = width!.Value, Height = height!.Value } : null
                    });
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new { Groups = groups }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"GetGroups failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /gh/group-resize - Resize a group to fit its members plus padding
        /// Body: { guid: string, padding?: number }
        /// </summary>
        public ApiResponse ResizeGroupToFit(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_group_resize");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_group_resize", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            string guidStr;
            float padding = 30f;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                guidStr = args!["guid"].GetString()!;
                if (args.TryGetValue("padding", out var p))
                    padding = (float)p.GetDouble();
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid body. Expected: {{ guid: string, padding?: number }}. Error: {ex.Message}" };
            }

            if (!Guid.TryParse(guidStr, out var groupGuid))
                return new ApiResponse { Success = false, Data = $"Invalid GUID: {guidStr}" };

            try
            {
                var groupType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Group");
                if (groupType == null)
                    return new ApiResponse { Success = false, Data = "GH_Group type not found" };

                // Find the group object
                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;
                if (objects == null)
                    return new ApiResponse { Success = false, Data = "No objects in document" };

                object? targetGroup = null;
                foreach (var obj in objects)
                {
                    if (!groupType.IsInstanceOfType(obj))
                        continue;
                    var gp = obj.GetType().GetProperty("InstanceGuid");
                    if (gp != null && ((Guid)gp.GetValue(obj)!) == groupGuid)
                    {
                        targetGroup = obj;
                        break;
                    }
                }

                if (targetGroup == null)
                    return new ApiResponse { Success = false, Data = $"Group not found: {guidStr}" };

                // Get member objects and compute union bounds
                RectangleF unionBounds = RectangleF.Empty;
                int memberCount = 0;

                // Try ObjectIDs first, then Objects() method
                var memberGuids = new List<Guid>();
                var objectIdsMethod = targetGroup.GetType().GetMethod("ObjectIDs");
                if (objectIdsMethod != null)
                {
                    var ids = objectIdsMethod.Invoke(targetGroup, null) as System.Collections.IEnumerable;
                    if (ids != null)
                    {
                        foreach (var id in ids)
                        {
                            if (id is Guid g) memberGuids.Add(g);
                        }
                    }
                }

                // Find member objects and compute union bounds
                foreach (var obj in objects)
                {
                    var gp = obj.GetType().GetProperty("InstanceGuid");
                    if (gp == null) continue;
                    var objGuid = (Guid)gp.GetValue(obj)!;

                    if (memberGuids.Count > 0 && !memberGuids.Contains(objGuid))
                        continue;
                    if (memberGuids.Count == 0)
                        continue; // Can't determine members

                    var attrProp = obj.GetType().GetProperty("Attributes");
                    if (attrProp == null) continue;
                    var attr = attrProp.GetValue(obj);
                    if (attr == null) continue;

                    var boundsProp = attr.GetType().GetProperty("Bounds");
                    if (boundsProp == null) continue;
                    var bounds = boundsProp.GetValue(attr);
                    if (bounds is RectangleF rf)
                    {
                        if (unionBounds.IsEmpty)
                            unionBounds = rf;
                        else
                            unionBounds = RectangleF.Union(unionBounds, rf);
                        memberCount++;
                    }
                }

                if (memberCount == 0)
                    return new ApiResponse { Success = false, Data = "No member objects found with bounds" };

                // Expand by padding
                unionBounds.Inflate(padding, padding);

                // Record layout undo BEFORE changing group bounds
                try
                {
                    var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                    if (undoUtil != null)
                        RecordLayoutUndoEvent(undoUtil, "Rook: resize group", targetGroup);
                }
                catch { /* undo recording is best-effort */ }

                // Set the group's bounds via Attributes
                var groupAttrProp = targetGroup.GetType().GetProperty("Attributes");
                if (groupAttrProp != null)
                {
                    var groupAttr = groupAttrProp.GetValue(targetGroup);
                    if (groupAttr != null)
                    {
                        var groupBoundsProp = groupAttr.GetType().GetProperty("Bounds");
                        if (groupBoundsProp != null && groupBoundsProp.CanWrite)
                        {
                            groupBoundsProp.SetValue(groupAttr, unionBounds);
                        }
                    }
                }

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Resized = true,
                        Guid = guidStr,
                        Members = memberCount,
                        Bounds = new { X = unionBounds.X, Y = unionBounds.Y, Width = unionBounds.Width, Height = unionBounds.Height }
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"ResizeGroupToFit failed: {ex.Message}" };
            }
        }

        #endregion

        #region Component Library & Discovery

        /// <summary>
        /// GET /gh/library?search=box&category=Surface&limit=20 - Search available GH components
        /// When audit=true, returns ALL components (including obsolete/hidden) with
        /// Obsolete flag and Exposure value for catalog maintenance.
        /// </summary>
        public ApiResponse SearchLibrary(string? search, string? category, int limit = 50, bool audit = false, bool exact = false)
        {
            var componentServer = GetGrasshopperComponentServerNoCanvas();
            if (!componentServer.Success)
                return new ApiResponse { Success = false, Data = componentServer.Error };

            try
            {
                var server = componentServer.Server!;
                if (audit)
                    return SearchLibraryAuditUnchanged(server, search, category, exact);

                return SearchLibraryFromComponentServer(server, search, category, limit, exact);
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"SearchLibrary failed: {ex.Message}"
                };
            }
        }

        internal ApiResponse SearchLibraryFromComponentServer(
            object server,
            string? search,
            string? category,
            int limit,
            bool exact)
        {
            try
            {
                var proxySnapshot = ReadObjectProxySnapshot(server);
                var hasSearch = !string.IsNullOrEmpty(search);
                var hasCategory = !string.IsNullOrEmpty(category);
                var candidates = new List<LibraryCandidate>();

                if (hasSearch)
                {
                    var findObjects = RequireHostMethod(server.GetType(), "FindObjects", 4);
                    var arguments = new object?[]
                    {
                        new[] { search! },
                        proxySnapshot.Count,
                        null,
                        null
                    };
                    var returnValue = findObjects.Invoke(server, arguments);
                    if (returnValue is not int returnedCount ||
                        arguments[2] is not Array foundProxies ||
                        arguments[3] is not Array foundScores ||
                        returnedCount != foundProxies.Length ||
                        returnedCount != foundScores.Length)
                    {
                        throw new InvalidOperationException("FindObjects returned an incomplete candidate projection.");
                    }

                    for (var index = 0; index < returnedCount; index++)
                    {
                        var proxy = foundProxies.GetValue(index)
                            ?? throw new InvalidOperationException("FindObjects returned a null proxy.");
                        var scoreValue = foundScores.GetValue(index);
                        if (scoreValue is not double score || double.IsNaN(score) || double.IsInfinity(score))
                            throw new InvalidOperationException("FindObjects returned an invalid native score.");
                        candidates.Add(ProjectLibraryCandidate(
                            proxy,
                            score,
                            exact ? "exact_name" : "native_search"));
                    }
                }
                else
                {
                    foreach (var proxy in proxySnapshot)
                        candidates.Add(ProjectLibraryCandidate(proxy, null, null));
                }

                var filtered = candidates
                    .Where(candidate => !candidate.Obsolete && (candidate.Exposure & 16) == 0)
                    .Where(candidate => !hasCategory ||
                        ContainsOrdinalIgnoreCase(candidate.Category, category!) ||
                        ContainsOrdinalIgnoreCase(candidate.SubCategory, category!))
                    .Where(candidate => !hasSearch || !exact ||
                        string.Equals(candidate.Name, search, StringComparison.OrdinalIgnoreCase))
                    .ToList();

                var compareProxies = RequireHostMethod(server.GetType(), "CompareProxies", 2);
                filtered.Sort((left, right) =>
                {
                    if (hasSearch)
                    {
                        var leftScore = left.NativeScore
                            ?? throw new InvalidOperationException("Search candidate lacked a native score.");
                        var rightScore = right.NativeScore
                            ?? throw new InvalidOperationException("Search candidate lacked a native score.");
                        var scoreComparison = rightScore.CompareTo(leftScore);
                        if (scoreComparison != 0)
                            return scoreComparison;
                    }

                    var proxyComparisonValue = compareProxies.Invoke(server, new[] { left.Proxy, right.Proxy });
                    if (proxyComparisonValue is not int proxyComparison)
                        throw new InvalidOperationException("CompareProxies returned a non-integer result.");
                    return proxyComparison != 0
                        ? proxyComparison
                        : StringComparer.Ordinal.Compare(left.Guid, right.Guid);
                });

                var returned = filtered
                    .Take(Math.Max(0, limit))
                    .Select(candidate => CandidatePayload(
                        candidate,
                        hasSearch ? CandidatePayloadShape.Search : CandidatePayloadShape.Catalog))
                    .ToList();

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Count = returned.Count,
                        ReturnedCount = returned.Count,
                        TotalMatches = filtered.Count,
                        Truncated = returned.Count < filtered.Count,
                        Components = returned
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"SearchLibrary failed: {UnwrapInvocationException(ex).Message}"
                };
            }
        }

        private ApiResponse SearchLibraryAuditUnchanged(
            object server,
            string? search,
            string? category,
            bool exact)
        {
            var proxiesProp = server.GetType().GetProperty("ObjectProxies");
            var proxies = proxiesProp?.GetValue(server) as System.Collections.IEnumerable;
            if (proxies == null)
                return new ApiResponse { Success = false, Data = "Could not retrieve proxies" };

            var results = new List<object>();
            var searchLower = search?.ToLowerInvariant();
            var totalScanned = 0;
            var obsoleteCount = 0;
            var hiddenCount = 0;

            foreach (var proxy in proxies)
            {
                var desc = proxy.GetType().GetProperty("Desc")?.GetValue(proxy);
                var name = desc?.GetType().GetProperty("Name")?.GetValue(desc)?.ToString() ?? "";
                var nickname = desc?.GetType().GetProperty("NickName")?.GetValue(desc)?.ToString();
                var componentDescription = desc?.GetType().GetProperty("Description")?.GetValue(desc)?.ToString();
                var componentCat = desc?.GetType().GetProperty("Category")?.GetValue(desc)?.ToString();
                var componentSubCat = desc?.GetType().GetProperty("SubCategory")?.GetValue(desc)?.ToString();
                var guid = proxy.GetType().GetProperty("Guid")?.GetValue(proxy)?.ToString();
                var obsolete = proxy.GetType().GetProperty("Obsolete")?.GetValue(proxy) as bool? ?? false;

                var exposure = ReadExposure(proxy);
                var flags = new List<string>();
                if ((exposure & 1) != 0) flags.Add("primary");
                if ((exposure & 2) != 0) flags.Add("secondary");
                if ((exposure & 4) != 0) flags.Add("tertiary");
                if ((exposure & 8) != 0) flags.Add("quarantine");
                if ((exposure & 16) != 0) flags.Add("hidden");
                if ((exposure & 32) != 0) flags.Add("obscure");
                var exposureLabel = flags.Count > 0 ? string.Join("|", flags) : "none";

                totalScanned++;
                if (obsolete) obsoleteCount++;
                if ((exposure & 16) != 0) hiddenCount++;

                if (category is { Length: > 0 })
                {
                    var filterCatLower = category.ToLowerInvariant();
                    var catMatches = (componentCat ?? "").ToLowerInvariant().Contains(filterCatLower) ||
                                     (componentSubCat ?? "").ToLowerInvariant().Contains(filterCatLower);
                    if (!catMatches) continue;
                }

                if (!string.IsNullOrEmpty(searchLower))
                {
                    var matches = exact
                        ? name.ToLowerInvariant() == searchLower
                        : name.ToLowerInvariant().Contains(searchLower) ||
                          (nickname?.ToLowerInvariant().Contains(searchLower) ?? false) ||
                          (componentDescription?.ToLowerInvariant().Contains(searchLower) ?? false);
                    if (!matches) continue;
                }

                if (obsolete || (exposure & 16) != 0 || (exposure & 8) != 0)
                {
                    results.Add(new
                    {
                        Name = name,
                        NickName = nickname,
                        Category = componentCat,
                        SubCategory = componentSubCat,
                        Guid = guid,
                        Obsolete = obsolete,
                        Exposure = exposure,
                        ExposureLabel = exposureLabel
                    });
                }
            }

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    TotalScanned = totalScanned,
                    DeprecatedCount = results.Count,
                    ObsoleteCount = obsoleteCount,
                    HiddenCount = hiddenCount,
                    Components = results
                }
            };
        }

        private static List<object> ReadObjectProxySnapshot(object server)
        {
            var proxiesValue = RequireHostProperty(server, "ObjectProxies");
            if (proxiesValue is not System.Collections.IEnumerable proxies)
                throw new InvalidOperationException("ObjectProxies was not enumerable.");

            var snapshot = new List<object>();
            foreach (var proxy in proxies)
                snapshot.Add(proxy ?? throw new InvalidOperationException("ObjectProxies contained null."));
            return snapshot;
        }

        private static LibraryCandidate ProjectLibraryCandidate(
            object proxy,
            double? nativeScore,
            string? matchSource)
        {
            var desc = RequireHostProperty(proxy, "Desc")
                ?? throw new InvalidOperationException("Proxy Desc was null.");
            var guidValue = RequireHostProperty(proxy, "Guid");
            if (guidValue is not Guid guid)
                throw new InvalidOperationException("Proxy Guid was not a GUID.");
            var obsoleteValue = RequireHostProperty(proxy, "Obsolete");
            if (obsoleteValue is not bool obsolete)
                throw new InvalidOperationException("Proxy Obsolete was not boolean.");

            return new LibraryCandidate
            {
                Proxy = proxy,
                Name = RequireHostString(desc, "Name"),
                NickName = ReadNullableHostString(desc, "NickName"),
                Description = ReadNullableHostString(desc, "Description"),
                Category = ReadNullableHostString(desc, "Category"),
                SubCategory = ReadNullableHostString(desc, "SubCategory"),
                Guid = guid.ToString("D").ToLowerInvariant(),
                SourceKind = ReadSourceKind(proxy),
                Obsolete = obsolete,
                Exposure = ReadExposure(proxy),
                NativeScore = nativeScore,
                MatchSource = matchSource
            };
        }

        private static object CandidatePayload(
            LibraryCandidate candidate,
            CandidatePayloadShape shape)
        {
            if (shape == CandidatePayloadShape.Search)
            {
                if (candidate.NativeScore == null ||
                    candidate.MatchSource is not ("native_search" or "exact_name"))
                    throw new InvalidOperationException("Search candidate lacked search evidence.");
                return new
                {
                    candidate.Name,
                    candidate.NickName,
                    candidate.Description,
                    candidate.Category,
                    candidate.SubCategory,
                    candidate.Guid,
                    candidate.SourceKind,
                    NativeScore = candidate.NativeScore!.Value,
                    candidate.MatchSource
                };
            }

            if (shape == CandidatePayloadShape.Ambiguity)
            {
                if (candidate.NativeScore != null || candidate.MatchSource != "exact_name")
                    throw new InvalidOperationException("Ambiguity candidate had invalid match evidence.");
                return new
                {
                    candidate.Name,
                    candidate.NickName,
                    candidate.Description,
                    candidate.Category,
                    candidate.SubCategory,
                    candidate.Guid,
                    candidate.SourceKind,
                    candidate.NativeScore,
                    candidate.MatchSource
                };
            }

            if (shape == CandidatePayloadShape.Catalog)
            {
                if (candidate.NativeScore != null || candidate.MatchSource != null)
                    throw new InvalidOperationException("Catalog candidate carried match evidence.");

                return new
                {
                    candidate.Name,
                    candidate.NickName,
                    candidate.Description,
                    candidate.Category,
                    candidate.SubCategory,
                    candidate.Guid,
                    candidate.SourceKind
                };
            }

            throw new ArgumentOutOfRangeException(nameof(shape), shape, "Unknown candidate payload shape.");
        }

        private static object? RequireHostProperty(object owner, string propertyName)
        {
            var property = owner.GetType().GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance)
                ?? throw new InvalidOperationException($"Required host property {propertyName} was missing.");
            return property.GetValue(owner);
        }

        private static string RequireHostString(object owner, string propertyName)
        {
            var value = RequireHostProperty(owner, propertyName);
            return value as string
                ?? throw new InvalidOperationException($"Required host property {propertyName} was not a string.");
        }

        private static string? ReadNullableHostString(object owner, string propertyName)
        {
            var value = RequireHostProperty(owner, propertyName);
            if (value == null || value is string)
                return (string?)value;
            throw new InvalidOperationException($"Host property {propertyName} was not a string or null.");
        }

        private static string ReadSourceKind(object proxy)
        {
            var value = RequireHostProperty(proxy, "Kind")
                ?? throw new InvalidOperationException("Proxy Kind was null.");
            if (!value.GetType().IsEnum)
                throw new InvalidOperationException("Proxy Kind was not an enum.");
            return value.ToString() switch
            {
                "CompiledObject" => "compiled",
                "UserObject" => "user_object",
                _ => throw new InvalidOperationException("Proxy Kind was unsupported.")
            };
        }

        private static int ReadExposure(object proxy)
        {
            var value = RequireHostProperty(proxy, "Exposure")
                ?? throw new InvalidOperationException("Proxy Exposure was null.");
            var type = value.GetType();
            if (!type.IsEnum)
                throw new InvalidOperationException("Proxy Exposure was not an enum.");
            return Convert.ToInt32(value);
        }

        private static MethodInfo RequireHostMethod(Type ownerType, string methodName, int parameterCount)
        {
            var matches = ownerType
                .GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
                .Where(method => method.Name == methodName && method.GetParameters().Length == parameterCount)
                .ToArray();
            return matches.Length == 1
                ? matches[0]
                : throw new InvalidOperationException($"Expected one host method {methodName}/{parameterCount}.");
        }

        private static bool ContainsOrdinalIgnoreCase(string? value, string search) =>
            value?.IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0;

        private static Exception UnwrapInvocationException(Exception exception) =>
            exception is TargetInvocationException { InnerException: not null } invocation
                ? invocation.InnerException
                : exception;

        private sealed class LibraryCandidate
        {
            public object Proxy { get; init; } = null!;
            public string Name { get; init; } = null!;
            public string? NickName { get; init; }
            public string? Description { get; init; }
            public string? Category { get; init; }
            public string? SubCategory { get; init; }
            public string Guid { get; init; } = null!;
            public string SourceKind { get; init; } = null!;
            public bool Obsolete { get; init; }
            public int Exposure { get; init; }
            public double? NativeScore { get; init; }
            public string? MatchSource { get; init; }
        }

        private enum CandidatePayloadShape
        {
            Catalog,
            Search,
            Ambiguity
        }

        /// <summary>
        /// GET /gh/categories - List all available component categories with counts
        /// </summary>
        public ApiResponse GetCategories()
        {
            var componentServer = GetGrasshopperComponentServerNoCanvas();
            if (!componentServer.Success)
                return new ApiResponse { Success = false, Data = componentServer.Error };

            try
            {
                var server = componentServer.Server!;

                var proxiesProp = server.GetType().GetProperty("ObjectProxies");
                var proxies = proxiesProp?.GetValue(server) as System.Collections.IEnumerable;

                if (proxies == null)
                    return new ApiResponse { Success = false, Data = "Could not retrieve proxies" };

                // Group by category and subcategory
                var categoryData = new Dictionary<string, Dictionary<string, int>>();
                int totalComponents = 0;

                foreach (var proxy in proxies)
                {
                    var obsoleteProp = proxy.GetType().GetProperty("Obsolete");
                    var obsolete = obsoleteProp?.GetValue(proxy) as bool? ?? false;
                    if (obsolete) continue;

                    var descProp = proxy.GetType().GetProperty("Desc");
                    var desc = descProp?.GetValue(proxy);

                    var categoryProp = desc?.GetType().GetProperty("Category");
                    var cat = categoryProp?.GetValue(desc)?.ToString() ?? "Unknown";

                    var subcategoryProp = desc?.GetType().GetProperty("SubCategory");
                    var subcat = subcategoryProp?.GetValue(desc)?.ToString() ?? "General";

                    if (!categoryData.ContainsKey(cat))
                        categoryData[cat] = new Dictionary<string, int>();

                    if (!categoryData[cat].ContainsKey(subcat))
                        categoryData[cat][subcat] = 0;

                    categoryData[cat][subcat]++;
                    totalComponents++;
                }

                // Convert to output format
                var categories = categoryData.Select(kvp => new
                {
                    Name = kvp.Key,
                    ComponentCount = kvp.Value.Values.Sum(),
                    SubCategories = kvp.Value.Select(sub => new
                    {
                        Name = sub.Key,
                        ComponentCount = sub.Value
                    }).OrderBy(s => s.Name).ToList()
                }).OrderBy(c => c.Name).ToList();

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        TotalCategories = categories.Count,
                        TotalComponents = totalComponents,
                        Categories = categories
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"GetCategories failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// Create a component instance from a GUID using 3-tier resolution:
        /// 1. Proxy GUID lookup in ObjectProxies → CreateInstance (handles GhPython/proxy GUIDs)
        /// 2. EmitObject (handles native C# component GUIDs where proxy GUID == runtime GUID)
        /// 3. Name scan fallback (only when fallbackName is provided)
        /// </summary>
        private object? CreateComponentFromGuid(object server, Guid guid, string? fallbackName)
        {
            var diag = new System.Text.StringBuilder();
            diag.AppendLine($"DIAG: guid={guid}, fallbackName={fallbackName ?? "(null)"}");

            // Tier 1: Find proxy by GUID in ObjectProxies, call CreateInstance.
            var guidStr_lookup = guid.ToString();
            var proxies = server.GetType().GetProperty("ObjectProxies")?.GetValue(server)
                as System.Collections.IEnumerable;
            diag.AppendLine($"DIAG: proxies={proxies != null}");
            int proxyCount = 0;
            int tier1Match = 0;
            if (proxies != null)
            {
                foreach (var p in proxies)
                {
                    proxyCount++;
                    var proxyGuidStr = p.GetType().GetProperty("Guid")?.GetValue(p)?.ToString() ?? "";
                    if (string.Equals(proxyGuidStr, guidStr_lookup, StringComparison.OrdinalIgnoreCase))
                    {
                        tier1Match++;
                        var createMethod = p.GetType().GetMethod("CreateInstance");
                        diag.AppendLine($"DIAG: Tier1 MATCH! proxy.Guid={proxyGuidStr}, CreateInstance method={createMethod != null}");
                        if (createMethod != null)
                        {
                            try
                            {
                                var instance = createMethod.Invoke(p, null);
                                diag.AppendLine($"DIAG: Tier1 CreateInstance result={instance != null}, type={instance?.GetType().Name ?? "null"}");
                                if (instance != null)
                                    return instance;
                            }
                            catch (Exception ex)
                            {
                                diag.AppendLine($"DIAG: Tier1 CreateInstance EXCEPTION: {ex.Message}");
                            }
                        }
                    }
                }
            }
            diag.AppendLine($"DIAG: Tier1 scanned {proxyCount} proxies, {tier1Match} matches");

            // Tier 2: Direct EmitObject
            var emitMethod = server.GetType().GetMethod("EmitObject", new[] { typeof(Guid) });
            var component = emitMethod?.Invoke(server, new object[] { guid });
            diag.AppendLine($"DIAG: Tier2 EmitObject result={component != null}");
            if (component != null)
                return component;

            // Tier 3: Name scan fallback
            int tier3Match = 0;
            if (!string.IsNullOrEmpty(fallbackName) && proxies != null)
            {
                var nameLower = fallbackName.ToLowerInvariant();
                foreach (var p in proxies)
                {
                    var desc = p.GetType().GetProperty("Desc")?.GetValue(p);
                    var pName = desc?.GetType().GetProperty("Name")?.GetValue(desc)?.ToString() ?? "";
                    var pNick = desc?.GetType().GetProperty("NickName")?.GetValue(desc)?.ToString() ?? "";
                    if (pName.ToLowerInvariant() == nameLower || pNick.ToLowerInvariant() == nameLower)
                    {
                        tier3Match++;
                        diag.AppendLine($"DIAG: Tier3 name match: Name={pName}, Nick={pNick}");
                        var inst = p.GetType().GetMethod("CreateInstance")?.Invoke(p, null);
                        diag.AppendLine($"DIAG: Tier3 CreateInstance result={inst != null}");
                        if (inst != null)
                            return inst;
                    }
                }
            }
            diag.AppendLine($"DIAG: Tier3 {tier3Match} name matches (fallbackName={fallbackName ?? "(null)"})");

            // Store diag for the caller to include in error
            _lastCreateDiag = diag.ToString();
            return null;
        }

        // Temporary diagnostic field
        private string? _lastCreateDiag;

        /// <summary>
        /// POST /gh/create-component - Create a component by name or GUID
        /// Body: { name?: string, guid?: string, x?: number, y?: number }
        /// </summary>
        internal ApiResponse CreateComponent(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_create_component");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_create_component", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            string? name = null;
            string? guidStr = null;
            float x = 100, y = 100;

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args != null)
                {
                    if (args.TryGetValue("name", out var n)) name = n.GetString();
                    if (args.TryGetValue("guid", out var g)) guidStr = g.GetString();
                    if (args.TryGetValue("x", out var xEl)) x = xEl.GetSingle();
                    if (args.TryGetValue("y", out var yEl)) y = yEl.GetSingle();
                }
            }
            catch
            {
                return new ApiResponse { Success = false, Data = "Invalid JSON body" };
            }

            if (string.IsNullOrEmpty(name) && string.IsNullOrEmpty(guidStr))
                return new ApiResponse { Success = false, Data = "Must provide 'name' or 'guid'" };

            try
            {
                var instancesType = gh.Assembly!.GetType("Grasshopper.Instances");
                var serverProp = instancesType?.GetProperty("ComponentServer", BindingFlags.Public | BindingFlags.Static);
                var server = serverProp?.GetValue(null);

                if (server == null)
                    return new ApiResponse { Success = false, Data = "ComponentServer not available" };

                object? component = null;

                if (!string.IsNullOrEmpty(guidStr) && Guid.TryParse(guidStr, out var componentGuid))
                {
                    // Create by GUID — proxy-first resolution (handles GhPython + native)
                    component = CreateComponentFromGuid(server, componentGuid, name);
                }
                else if (!string.IsNullOrEmpty(name))
                {
                    // Find component by name — detect ambiguity
                    var proxiesProp = server.GetType().GetProperty("ObjectProxies");
                    var proxies = proxiesProp?.GetValue(server) as System.Collections.IEnumerable;

                    var nameLower = name.ToLowerInvariant();
                    const int maxMatches = 5; // enough for ambiguity warning, avoids full 2000+ scan
                    var matches = new List<(object proxy, string fullName, string guid)>();
                    if (proxies == null)
                        return new ApiResponse { Success = false, Data = "ObjectProxies not available" };
                    foreach (var proxy in proxies)
                    {
                        var descProp = proxy.GetType().GetProperty("Desc");
                        var desc = descProp?.GetValue(proxy);
                        var nameVal = desc?.GetType().GetProperty("Name")?.GetValue(desc)?.ToString() ?? "";
                        var nicknameVal = desc?.GetType().GetProperty("NickName")?.GetValue(desc)?.ToString() ?? "";

                        if (nameVal.ToLowerInvariant() == nameLower || nicknameVal.ToLowerInvariant() == nameLower)
                        {
                            var compGuidProp = desc?.GetType().GetProperty("Guid");
                            var compGuid = compGuidProp?.GetValue(desc)?.ToString() ?? "?";
                            var category = desc?.GetType().GetProperty("Category")?.GetValue(desc)?.ToString() ?? "";
                            var subcat = desc?.GetType().GetProperty("SubCategory")?.GetValue(desc)?.ToString() ?? "";
                            matches.Add((proxy, $"{nameVal} ({category}/{subcat}) GUID={compGuid}", compGuid));
                            if (matches.Count >= maxMatches)
                                break;
                        }
                    }

                    if (matches.Count == 0)
                        return new ApiResponse { Success = false, Data = $"Component '{name}' not found" };

                    if (matches.Count > 1)
                    {
                        return new ApiResponse
                        {
                            Success = false,
                            Data = $"Ambiguous component name '{name}'. Use GUID instead. Matches: [{string.Join(", ", matches.Select(m => m.fullName))}]"
                        };
                    }

                    var createMethod = matches[0].proxy.GetType().GetMethod("CreateInstance");
                    component = createMethod?.Invoke(matches[0].proxy, null);

                    if (component == null)
                        return new ApiResponse { Success = false, Data = $"Component '{name}' found but CreateInstance returned null" };
                }

                if (component == null)
                {
                    var diagMsg = _lastCreateDiag ?? "no diagnostics";
                    return new ApiResponse { Success = false, Data = $"Failed to create component instance. Diag: {diagMsg}" };
                }

                // Create attributes and set position
                var createAttrMethod = component.GetType().GetMethod("CreateAttributes", BindingFlags.Public | BindingFlags.Instance);
                createAttrMethod?.Invoke(component, null);

                var attrProp = component.GetType().GetProperty("Attributes");
                if (attrProp != null)
                {
                    var attr = attrProp.GetValue(component);
                    var pivotProp = attr?.GetType().GetProperty("Pivot");
                    pivotProp?.SetValue(attr, new PointF(x, y));
                }

                // Add to document
                var resultGuid = AddObjectToDocument(gh.Document!, component);

                // Record undo for component creation
                try
                {
                    var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                    if (undoUtil != null)
                        RecordUndoEvent(undoUtil, "Rook: create component", new List<object> { component }, isAdd: true);
                }
                catch { /* undo recording is best-effort */ }

                RefreshCanvas(gh.Canvas!);

                // Get component info
                var compName = component.GetType().GetProperty("Name")?.GetValue(component)?.ToString();
                var compNickname = component.GetType().GetProperty("NickName")?.GetValue(component)?.ToString();

                // Get params info
                var paramsInfo = GetComponentParams(component);

                var responseData = new Dictionary<string, object?>
                {
                    ["created"] = true,
                    ["type"] = component.GetType().Name,
                    ["name"] = compName,
                    ["nickName"] = compNickname,
                    ["guid"] = resultGuid,
                    ["position"] = new { X = x, Y = y },
                    ["params"] = paramsInfo,
                };

                return new ApiResponse { Success = true, Data = responseData };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"CreateComponent failed: {ex.InnerException?.Message ?? ex.Message}"
                };
            }
        }

        /// <summary>
        /// GET /gh/component?guid=xxx - Get detailed info about a component including params
        /// </summary>
        internal ApiResponse GetComponentInfo(string? guid)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_component");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_component", null, gh.Error);

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var target = FindObjectById(gh.Document!, guid);
                if (target == null)
                    return new ApiResponse { Success = false, Data = $"Object not found: {guid}" };

                var paramsInfo = GetComponentParams(target);
                var runtimeMessages = GetRuntimeMessages(target);
                var category = target.GetType().GetProperty("Category")?.GetValue(target)?.ToString();
                var subCategory = target.GetType().GetProperty("SubCategory")?.GetValue(target)?.ToString();

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Type = target.GetType().Name,
                        Name = target.GetType().GetProperty("Name")?.GetValue(target)?.ToString(),
                        NickName = target.GetType().GetProperty("NickName")?.GetValue(target)?.ToString(),
                        Description = target.GetType().GetProperty("Description")?.GetValue(target)?.ToString(),
                        Category = category ?? "",
                        SubCategory = subCategory ?? "",
                        Guid = guid,
                        Params = paramsInfo,
                        RuntimeMessages = runtimeMessages
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"GetComponentInfo failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// GET /gh/errors - Get all components with runtime errors or warnings
        /// Returns list of components with their error/warning messages and input states
        /// </summary>
        public ApiResponse GetCanvasErrors(bool debug = false)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_errors");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_errors", null, gh.Error);

            try
            {
                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;

                var componentsWithErrors = new List<object>();
                var componentsWithWarnings = new List<object>();
                var debugComponents = new List<object>();
                int totalComponents = 0;

                foreach (var obj in objects!)
                {
                    // Skip non-components (like wires)
                    var typeName = obj.GetType().Name;
                    if (typeName.Contains("Wire")) continue;

                    totalComponents++;

                    // Get component identity first (need for debug output)
                    var guidProp = obj.GetType().GetProperty("InstanceGuid");
                    var guid = guidProp?.GetValue(obj)?.ToString() ?? "";
                    var name = obj.GetType().GetProperty("Name")?.GetValue(obj)?.ToString() ?? typeName;
                    var nickName = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString() ?? "";

                    var messages = GetRuntimeMessages(obj, debug);

                    // In debug mode, collect info about all components
                    if (debug)
                    {
                        var msgType = messages?.GetType();
                        var debugList = msgType?.GetProperty("Debug")?.GetValue(messages) as List<string> ?? new List<string>();
                        debugComponents.Add(new
                        {
                            Guid = guid,
                            Name = name,
                            NickName = nickName,
                            Type = typeName,
                            Debug = debugList,
                            HasMessages = messages != null
                        });
                    }

                    if (messages == null) continue;

                    // Get input connection state
                    var inputStates = new List<object>();
                    var paramsProp = obj.GetType().GetProperty("Params");
                    if (paramsProp != null)
                    {
                        var paramsObj = paramsProp.GetValue(obj);
                        var inputProp = paramsObj?.GetType().GetProperty("Input");
                        var inputs = inputProp?.GetValue(paramsObj) as System.Collections.IEnumerable;
                        if (inputs != null)
                        {
                            foreach (var input in inputs)
                            {
                                var inputNick = input.GetType().GetProperty("NickName")?.GetValue(input)?.ToString() ?? "?";
                                var sourcesProp = input.GetType().GetProperty("Sources");
                                var sources = sourcesProp?.GetValue(input) as System.Collections.IEnumerable;
                                var sourceCount = sources?.Cast<object>().Count() ?? 0;
                                var isOptional = input.GetType().GetProperty("Optional")?.GetValue(input) as bool? ?? false;

                                inputStates.Add(new
                                {
                                    Name = inputNick,
                                    Connected = sourceCount > 0,
                                    SourceCount = sourceCount,
                                    Optional = isOptional
                                });
                            }
                        }
                    }

                    // Extract warnings and errors from messages
                    var msgType2 = messages.GetType();
                    var warnings = msgType2.GetProperty("Warnings")?.GetValue(messages) as List<string> ?? new List<string>();
                    var errors = msgType2.GetProperty("Errors")?.GetValue(messages) as List<string> ?? new List<string>();

                    var componentInfo = new
                    {
                        Guid = guid,
                        Name = name,
                        NickName = nickName,
                        Type = typeName,
                        Inputs = inputStates,
                        Warnings = warnings,
                        Errors = errors
                    };

                    if (errors.Count > 0)
                        componentsWithErrors.Add(componentInfo);
                    else if (warnings.Count > 0)
                        componentsWithWarnings.Add(componentInfo);
                }

                if (debug)
                {
                    return new ApiResponse
                    {
                        Success = true,
                        Data = new
                        {
                            TotalComponents = totalComponents,
                            ErrorCount = componentsWithErrors.Count,
                            WarningCount = componentsWithWarnings.Count,
                            Errors = componentsWithErrors,
                            Warnings = componentsWithWarnings,
                            DebugInfo = debugComponents
                        }
                    };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        TotalComponents = totalComponents,
                        ErrorCount = componentsWithErrors.Count,
                        WarningCount = componentsWithWarnings.Count,
                        Errors = componentsWithErrors,
                        Warnings = componentsWithWarnings
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"GetCanvasErrors failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// GET /gh/inspect-output?guid=xxx&amp;param=S or &amp;outputIndex=0 - Inspect output data structure
        /// Returns detailed info about output data: type, structure (single/list/tree), paths, counts
        /// </summary>
        public ApiResponse InspectOutput(string? guid, string? param, string? readinessReceiptId = null)
        {
            var selector = param is null
                ? default
                : new GhInspectOutputSelector(param, outputIndex: null);
            return InspectOutput(guid, selector, readinessReceiptId);
        }

        internal ApiResponse InspectOutput(
            string? guid,
            GhInspectOutputSelector selector,
            string? readinessReceiptId = null)
        {
            if (!GhInspectOutputSelectorResolver.TryValidate(selector, out var selectorError))
                return selectorError!.ToApiResponse();

            var notReady = EnsureGrasshopperReadyForEdit("gh_inspect_output");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_inspect_output", null, gh.Error);

            GhFencedReadGate? readinessGate = null;
            if (readinessReceiptId is not null)
            {
                if (string.IsNullOrWhiteSpace(readinessReceiptId))
                    return ReadinessIssueFailure("readiness_receipt_id_invalid");

                var gate = _solveReceiptRegistry.CheckFencedRead(
                    readinessReceiptId,
                    gh.Document!,
                    GrasshopperDispatchContext.Current?.DocumentId.ToString("D"));
                if (!gate.Allowed)
                    return ReadinessFenceFailure(gate);
                readinessGate = gate;
            }

            if (string.IsNullOrEmpty(guid))
                return new ApiResponse { Success = false, Data = "Missing guid parameter" };

            try
            {
                var target = FindObjectById(gh.Document!, guid);
                if (target == null)
                    return new ApiResponse { Success = false, Data = $"Object not found: {guid}" };

                // Get params
                var paramsProp = target.GetType().GetProperty("Params");
                if (paramsProp == null)
                    return new ApiResponse { Success = false, Data = "Object has no Params property (may be a slider/panel)" };

                var paramsVal = paramsProp.GetValue(target);
                var outputProp = paramsVal?.GetType().GetProperty("Output");
                var outputs = outputProp?.GetValue(paramsVal) as System.Collections.IList;

                if (outputs == null || outputs.Count == 0)
                    return new ApiResponse { Success = false, Data = "No outputs available" };

                if (!GhInspectOutputSelectorResolver.TryResolve(
                        outputs,
                        selector,
                        out var resolvedOutput,
                        out selectorError))
                {
                    return selectorError!.ToApiResponse();
                }

                var targetOutput = resolvedOutput.Value!;
                var outputIndex = resolvedOutput.Index;

                // Get output info
                var outputName = targetOutput.GetType().GetProperty("Name")?.GetValue(targetOutput)?.ToString();
                var outputNickname = targetOutput.GetType().GetProperty("NickName")?.GetValue(targetOutput)?.ToString();
                var typeName = targetOutput.GetType().GetProperty("TypeName")?.GetValue(targetOutput)?.ToString();

                // Try to get volatile data
                var volatileDataProp = targetOutput.GetType().GetProperty("VolatileData");
                var volatileData = volatileDataProp?.GetValue(targetOutput);

                var dataInfo = new Dictionary<string, object?>
                {
                    ["param_name"] = outputName,
                    ["param_nickname"] = outputNickname,
                    ["type_name"] = typeName,
                    ["index"] = outputIndex
                };

                if (volatileData != null)
                {
                    // Get structure info from the data tree
                    var isEmptyProp = volatileData.GetType().GetProperty("IsEmpty");
                    var isEmpty = isEmptyProp?.GetValue(volatileData) as bool? ?? true;

                    var pathCountProp = volatileData.GetType().GetProperty("PathCount");
                    var pathCount = pathCountProp?.GetValue(volatileData) as int? ?? 0;

                    var dataCountProp = volatileData.GetType().GetProperty("DataCount");
                    var dataCount = dataCountProp?.GetValue(volatileData) as int? ?? 0;

                    dataInfo["is_empty"] = isEmpty;
                    dataInfo["path_count"] = pathCount;
                    dataInfo["data_count"] = dataCount;

                    // Determine structure type
                    if (isEmpty)
                    {
                        dataInfo["structure"] = "empty";
                    }
                    else if (pathCount == 1 && dataCount == 1)
                    {
                        dataInfo["structure"] = "single";
                    }
                    else if (pathCount == 1)
                    {
                        dataInfo["structure"] = "list";
                    }
                    else
                    {
                        dataInfo["structure"] = "tree";
                    }

                    // Try to get branch paths
                    var pathsProp = volatileData.GetType().GetProperty("Paths");
                    var paths = pathsProp?.GetValue(volatileData) as System.Collections.IEnumerable;
                    if (paths != null)
                    {
                        var branchInfo = new List<object>();
                        foreach (var path in paths)
                        {
                            var pathStr = path?.ToString() ?? "";

                            // Get branch for this path
                            var getBranchMethod = volatileData.GetType().GetMethod("get_Branch", new[] { path.GetType() });
                            var branch = getBranchMethod?.Invoke(volatileData, new[] { path });
                            var branchCount = (branch as System.Collections.IList)?.Count ?? 0;

                            branchInfo.Add(new { path = pathStr, count = branchCount });
                        }
                        dataInfo["branches"] = branchInfo;
                    }

                    // Try to get first few values for preview
                    if (!isEmpty)
                    {
                        var allDataMethod = volatileData.GetType().GetMethod("AllData", new[] { typeof(bool) });
                        if (allDataMethod != null)
                        {
                            var allData = allDataMethod.Invoke(volatileData, new object[] { false }) as System.Collections.IEnumerable;
                            if (allData != null)
                            {
                                var preview = new List<string>();
                                int previewCount = 0;
                                foreach (var item in allData)
                                {
                                    if (previewCount >= 5) break;  // Limit preview to 5 items

                                    // Try to get the actual value
                                    var valueProp = item?.GetType().GetProperty("Value");
                                    var value = valueProp?.GetValue(item);
                                    preview.Add(value?.ToString() ?? item?.ToString() ?? "null");
                                    previewCount++;
                                }
                                dataInfo["preview"] = preview;
                                dataInfo["preview_note"] = dataCount > 5 ? $"Showing first 5 of {dataCount} items" : null;
                            }
                        }
                    }
                }
                else
                {
                    dataInfo["structure"] = "unknown";
                    dataInfo["note"] = "Could not access VolatileData";
                }

                if (readinessGate?.Receipt is GhSolveReadinessReceipt receipt)
                {
                    dataInfo["readiness_fenced"] = true;
                    dataInfo["readiness_receipt_id"] = receipt.ReceiptId;
                    dataInfo["document_session_id"] = receipt.DocumentSessionId;
                    dataInfo["mutation_epoch"] = receipt.MutationEpoch;
                    dataInfo["solution_run_epoch"] = receipt.SolutionRunEpoch;
                    dataInfo["completed_solution_run_epoch"] = receipt.CompletedSolutionRunEpoch;
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = dataInfo
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"InspectOutput failed: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/bake - Bake GH output geometry into the Rhino document with layer control.
        /// Explicit mode: { targets: [{ instanceGuid, outputIndex, outputName? }], layerName?, createSublayers?, clearExisting?, clearMode? }
        /// Convenience mode: { bakeAll: true, layerName?, createSublayers?, clearExisting?, clearMode? }
        /// </summary>
        public ApiResponse BakeOutput(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_bake_output");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_bake_output", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            // Parse request
            Dictionary<string, JsonElement>? args;
            try
            {
                args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args == null)
                    return new ApiResponse { Success = false, Data = "Invalid JSON body" };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid JSON: {ex.Message}" };
            }

            try
            {
                // Parse optional fields with ValueKind checks to avoid InvalidOperationException
                // on malformed input (e.g. "bakeAll":"yes" instead of true)
                bool hasTargets = args.TryGetValue("targets", out var targetsEl) && targetsEl.ValueKind == JsonValueKind.Array;
                bool hasBakeAll = args.TryGetValue("bakeAll", out var bakeAllEl) &&
                    bakeAllEl.ValueKind is JsonValueKind.True or JsonValueKind.False && bakeAllEl.GetBoolean();

                if (hasTargets && hasBakeAll)
                    return new ApiResponse { Success = false, Data = "Cannot specify both 'targets' and 'bakeAll'" };
                if (!hasTargets && !hasBakeAll)
                    return new ApiResponse { Success = false, Data = "Must specify either 'targets' or 'bakeAll'" };

                string layerName = args.TryGetValue("layerName", out var ln) && ln.ValueKind == JsonValueKind.String
                    ? ln.GetString() ?? "RookBake" : "RookBake";
                bool createSublayers = !args.TryGetValue("createSublayers", out var cs) ||
                    cs.ValueKind is not (JsonValueKind.True or JsonValueKind.False) || cs.GetBoolean();
                bool clearExisting = args.TryGetValue("clearExisting", out var ce) &&
                    ce.ValueKind is JsonValueKind.True or JsonValueKind.False && ce.GetBoolean();
                string? clearMode = args.TryGetValue("clearMode", out var cm) && cm.ValueKind == JsonValueKind.String
                    ? cm.GetString() : null;
                // Resolve targets
                List<BakeTargetDto> targets;
                if (hasBakeAll)
                {
                    targets = DiscoverBakeAllTargets(gh);
                    if (targets.Count == 0)
                        return new ApiResponse { Success = false, Data = "bakeAll found no component outputs with bakeable geometry" };
                }
                else
                {
                    var resolveResult = ResolveExplicitBakeTargets(gh, targetsEl);
                    if (!resolveResult.Success)
                        return new ApiResponse { Success = false, Data = resolveResult.Error };
                    targets = resolveResult.Targets;
                }

                // Delegate to BakeService
                var request = new BakeRequest
                {
                    Targets = targets,
                    LayerName = layerName,
                    CreateSublayers = createSublayers,
                    ClearExisting = clearExisting,
                    ClearMode = clearMode
                };

                var result = BakeService.Execute(request);

                return new ApiResponse
                {
                    Success = result.Success,
                    Data = result.Success
                        ? new Dictionary<string, object?>
                        {
                            ["totalBaked"] = result.TotalBaked,
                            ["totalSkipped"] = result.TotalSkipped,
                            ["perTarget"] = result.PerTarget.Select(t => new Dictionary<string, object?>
                            {
                                ["instanceGuid"] = t.InstanceGuid,
                                ["outputIndex"] = t.OutputIndex,
                                ["sublayer"] = t.Sublayer,
                                ["bakedCount"] = t.BakedCount,
                                ["bakedIds"] = t.BakedIds,
                                ["geometryTypes"] = t.GeometryTypes,
                                ["skippedCount"] = t.SkippedCount,
                                ["skippedReasons"] = t.SkippedReasons
                            }).ToList()
                        }
                        : (object?)result.Error
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"BakeOutput failed: {ex.Message}"
                };
            }
        }

        #region Bake Helpers

        private record BakeTargetResolveResult(bool Success, string? Error, List<BakeTargetDto> Targets);

        /// <summary>
        /// Resolve explicit targets from the request JSON. Validates instanceGuid, outputIndex,
        /// and optional outputName mismatch.
        /// </summary>
        private BakeTargetResolveResult ResolveExplicitBakeTargets(GrasshopperContext gh, JsonElement targetsEl)
        {
            var targets = new List<BakeTargetDto>();
            int idx = 0;

            foreach (var targetEl in targetsEl.EnumerateArray())
            {
                if (!targetEl.TryGetProperty("instanceGuid", out var guidEl))
                    return new BakeTargetResolveResult(false, $"targets[{idx}]: missing 'instanceGuid'", targets);

                string instanceGuid = guidEl.GetString() ?? "";

                // Resolve by short ID if needed
                var resolvedGuid = _idRegistry.Resolve(instanceGuid);
                string fullGuid = resolvedGuid?.ToString() ?? instanceGuid;

                var component = FindObjectById(gh.Document!, fullGuid);
                if (component == null)
                    return new BakeTargetResolveResult(false, $"targets[{idx}]: component not found: {instanceGuid}", targets);

                // Must have Params.Output
                var paramsProp = component.GetType().GetProperty("Params");
                if (paramsProp == null)
                    return new BakeTargetResolveResult(false, $"targets[{idx}]: object has no Params (not a component)", targets);

                var paramsVal = paramsProp.GetValue(component);
                var outputs = paramsVal?.GetType().GetProperty("Output")?.GetValue(paramsVal) as System.Collections.IList;
                if (outputs == null || outputs.Count == 0)
                    return new BakeTargetResolveResult(false, $"targets[{idx}]: component has no outputs", targets);

                bool hasOutputIndex = targetEl.TryGetProperty("outputIndex", out var outIdxEl) &&
                    outIdxEl.ValueKind == JsonValueKind.Number;
                string? requestedOutputName = targetEl.TryGetProperty("outputName", out var nameEl) &&
                    nameEl.ValueKind == JsonValueKind.String ? nameEl.GetString() : null;

                if (!hasOutputIndex && string.IsNullOrEmpty(requestedOutputName))
                    return new BakeTargetResolveResult(false, $"targets[{idx}]: must specify 'outputIndex' or 'outputName'", targets);

                int outputIndex;
                object output;

                if (hasOutputIndex)
                {
                    // Primary path: resolve by index
                    outputIndex = outIdxEl.GetInt32();
                    if (outputIndex < 0 || outputIndex >= outputs.Count)
                        return new BakeTargetResolveResult(false, $"targets[{idx}]: outputIndex {outputIndex} out of range (0..{outputs.Count - 1})", targets);

                    output = outputs[outputIndex]!;

                    // Validate outputName if also supplied (mismatch → reject)
                    if (!string.IsNullOrEmpty(requestedOutputName))
                    {
                        var actualName = output.GetType().GetProperty("Name")?.GetValue(output)?.ToString();
                        var actualNickname = output.GetType().GetProperty("NickName")?.GetValue(output)?.ToString();
                        if (!string.Equals(requestedOutputName, actualName, StringComparison.OrdinalIgnoreCase) &&
                            !string.Equals(requestedOutputName, actualNickname, StringComparison.OrdinalIgnoreCase))
                        {
                            return new BakeTargetResolveResult(false,
                                $"targets[{idx}]: outputName mismatch — requested '{requestedOutputName}' but output[{outputIndex}] is '{actualName}' (nickname: '{actualNickname}')",
                                targets);
                        }
                    }
                }
                else
                {
                    // Convenience path: resolve by name only
                    outputIndex = -1;
                    output = null!;
                    for (int i = 0; i < outputs.Count; i++)
                    {
                        var outParam = outputs[i]!;
                        var name = outParam.GetType().GetProperty("Name")?.GetValue(outParam)?.ToString();
                        var nick = outParam.GetType().GetProperty("NickName")?.GetValue(outParam)?.ToString();
                        if (string.Equals(requestedOutputName, name, StringComparison.OrdinalIgnoreCase) ||
                            string.Equals(requestedOutputName, nick, StringComparison.OrdinalIgnoreCase))
                        {
                            outputIndex = i;
                            output = outParam;
                            break;
                        }
                    }
                    if (outputIndex < 0)
                        return new BakeTargetResolveResult(false,
                            $"targets[{idx}]: no output named '{requestedOutputName}' on component {instanceGuid}", targets);
                }

                // Get component nickname for sublayer naming
                string? nickname = component.GetType().GetProperty("NickName")?.GetValue(component)?.ToString();

                // Extract items from VolatileData
                var items = ExtractBakeItems(output);
                if (items.Count == 0)
                {
                    // Not fatal — include with empty items so perTarget reports it
                }

                targets.Add(new BakeTargetDto
                {
                    InstanceGuid = fullGuid,
                    OutputIndex = outputIndex,
                    Nickname = nickname,
                    Items = items
                });

                idx++;
            }

            return new BakeTargetResolveResult(true, null, targets);
        }

        /// <summary>
        /// Discover bake targets for bakeAll mode. Only considers component outputs
        /// (objects with Params.Output), not standalone params or other canvas objects.
        /// </summary>
        private List<BakeTargetDto> DiscoverBakeAllTargets(GrasshopperContext gh)
        {
            var targets = new List<BakeTargetDto>();

            var objectsProp = gh.Document!.GetType().GetProperty("Objects");
            var objects = objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable;
            if (objects == null) return targets;

            foreach (var obj in objects)
            {
                // Must have Params property (components only)
                var paramsProp = obj.GetType().GetProperty("Params");
                if (paramsProp == null) continue;

                var paramsVal = paramsProp.GetValue(obj);
                var outputs = paramsVal?.GetType().GetProperty("Output")?.GetValue(paramsVal) as System.Collections.IList;
                if (outputs == null || outputs.Count == 0) continue;

                var instanceGuid = obj.GetType().GetProperty("InstanceGuid")?.GetValue(obj)?.ToString();
                if (string.IsNullOrEmpty(instanceGuid)) continue;

                var nickname = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString();

                for (int i = 0; i < outputs.Count; i++)
                {
                    var output = outputs[i]!;
                    var items = ExtractBakeItems(output);
                    if (items.Count == 0) continue;  // Skip empty outputs

                    // Check if any items contain bakeable geometry
                    bool hasBakeable = false;
                    foreach (var item in items)
                    {
                        if (BakeService.TryNormalizeBakeGeometry(item.Value, out _, out _, out _))
                        {
                            hasBakeable = true;
                            break;
                        }
                    }
                    if (!hasBakeable) continue;

                    targets.Add(new BakeTargetDto
                    {
                        InstanceGuid = instanceGuid,
                        OutputIndex = i,
                        Nickname = nickname,
                        Items = items
                    });
                }
            }

            return targets;
        }

        /// <summary>
        /// Extract BakeItems from a GH output parameter's VolatileData.
        /// Uses reflection to traverse the data tree: Paths → get_Branch → items → .Value
        /// Falls back to ScriptVariable() if .Value returns null.
        /// </summary>
        private List<BakeItem> ExtractBakeItems(object outputParam)
        {
            var items = new List<BakeItem>();

            try
            {
                var volatileData = outputParam.GetType().GetProperty("VolatileData")?.GetValue(outputParam);
                if (volatileData == null) return items;

                var isEmpty = volatileData.GetType().GetProperty("IsEmpty")?.GetValue(volatileData) as bool? ?? true;
                if (isEmpty) return items;

                var paths = volatileData.GetType().GetProperty("Paths")?.GetValue(volatileData) as System.Collections.IEnumerable;
                if (paths == null) return items;

                foreach (var path in paths)
                {
                    var pathStr = path?.ToString() ?? "{0}";

                    var getBranchMethod = volatileData.GetType().GetMethod("get_Branch", new[] { path!.GetType() });
                    var branch = getBranchMethod?.Invoke(volatileData, new[] { path }) as System.Collections.IList;
                    if (branch == null) continue;

                    for (int i = 0; i < branch.Count; i++)
                    {
                        var ghItem = branch[i];
                        if (ghItem == null) continue;

                        // Primary: read .Value
                        object? rawValue = null;
                        var valueProp = ghItem.GetType().GetProperty("Value");
                        if (valueProp != null)
                            rawValue = valueProp.GetValue(ghItem);

                        // Fallback: try ScriptVariable() if Value is null
                        if (rawValue == null)
                        {
                            var scriptVarMethod = ghItem.GetType().GetMethod("ScriptVariable");
                            if (scriptVarMethod != null)
                            {
                                try { rawValue = scriptVarMethod.Invoke(ghItem, null); }
                                catch { /* ignore fallback failure */ }
                            }
                        }

                        items.Add(new BakeItem
                        {
                            Value = rawValue,
                            BranchPath = pathStr,
                            ItemIndex = i
                        });
                    }
                }
            }
            catch
            {
                // Return whatever items we collected before failure
            }

            return items;
        }

        #endregion

        #endregion

        #region Wiring & Connections

        /// <summary>
        /// POST /gh/connect - Wire two components together
        /// Body: { sourceGuid: string, sourceParam?: string|int, sourceIndex?: int,
        ///         targetGuid: string, targetParam?: string|int, targetIndex?: int }
        /// </summary>
        internal ApiResponse ConnectComponents(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_connect");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_connect", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            if (!GhConnectionSelectorResolver.TryParseRequest(body!, out var request, out var parseError))
                return new ApiResponse { Success = false, Data = parseError };

            try
            {
                var sourceObj = FindObjectById(gh.Document!, request!.SourceGuid);
                if (sourceObj == null)
                    return new ApiResponse { Success = false, Data = $"Source object not found: {request.SourceGuid}" };
                var targetObj = FindObjectById(gh.Document!, request.TargetGuid);
                if (targetObj == null)
                    return new ApiResponse { Success = false, Data = $"Target object not found: {request.TargetGuid}" };

                if (!GhConnectionSelectorResolver.TryResolve(
                        sourceObj,
                        isInput: false,
                        request.SourceSelector,
                        out var resolvedSource,
                        out var sourceError))
                    return new ApiResponse { Success = false, Data = sourceError };
                if (!GhConnectionSelectorResolver.TryResolve(
                        targetObj,
                        isInput: true,
                        request.TargetSelector,
                        out var resolvedTarget,
                        out var targetError))
                    return new ApiResponse { Success = false, Data = targetError };

                var sourceOutput = resolvedSource.Value!;
                var targetInput = resolvedTarget.Value!;

                // Record wire undo BEFORE connecting
                try
                {
                    var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                    if (undoUtil != null)
                        RecordWireUndoEvent(undoUtil, "Rook: connect", new List<object> { targetInput });
                }
                catch { /* undo recording is best-effort */ }

                // Wire using AddSource
                var addSourceMethod = targetInput.GetType().GetMethod("AddSource",
                    new[] { gh.Assembly!.GetType("Grasshopper.Kernel.IGH_Param")! });

                if (addSourceMethod == null)
                    return new ApiResponse { Success = false, Data = "AddSource method not found" };

                addSourceMethod.Invoke(targetInput, new[] { sourceOutput });

                // Expire solution to recalculate
                var expireMethod = targetObj.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
                expireMethod?.Invoke(targetObj, new object[] { true });

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Connected = true,
                        Source = new
                        {
                            Guid = request.SourceGuid,
                            Param = resolvedSource.Name,
                            Index = resolvedSource.Index
                        },
                        Target = new
                        {
                            Guid = request.TargetGuid,
                            Param = resolvedTarget.Name,
                            Index = resolvedTarget.Index
                        }
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"ConnectComponents failed: {ex.InnerException?.Message ?? ex.Message}"
                };
            }
        }

        /// <summary>
        /// POST /gh/disconnect - Remove a wire between components
        /// Body: { sourceGuid: string, sourceParam?: string|int, sourceIndex?: int,
        ///         targetGuid: string, targetParam?: string|int, targetIndex?: int }
        /// </summary>
        internal ApiResponse DisconnectComponents(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_disconnect");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_disconnect", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            if (!GhConnectionSelectorResolver.TryParseRequest(body!, out var request, out var parseError))
                return new ApiResponse { Success = false, Data = parseError };

            try
            {
                var sourceObj = FindObjectById(gh.Document!, request!.SourceGuid);
                if (sourceObj == null)
                    return new ApiResponse { Success = false, Data = $"Source object not found: {request.SourceGuid}" };
                var targetObj = FindObjectById(gh.Document!, request.TargetGuid);
                if (targetObj == null)
                    return new ApiResponse { Success = false, Data = $"Target object not found: {request.TargetGuid}" };

                if (!GhConnectionSelectorResolver.TryResolve(
                        sourceObj,
                        isInput: false,
                        request.SourceSelector,
                        out var resolvedSource,
                        out var sourceError))
                    return new ApiResponse { Success = false, Data = sourceError };
                if (!GhConnectionSelectorResolver.TryResolve(
                        targetObj,
                        isInput: true,
                        request.TargetSelector,
                        out var resolvedTarget,
                        out var targetError))
                    return new ApiResponse { Success = false, Data = targetError };

                var sourceOutput = resolvedSource.Value!;
                var targetInput = resolvedTarget.Value!;

                // Record wire undo BEFORE disconnecting
                try
                {
                    var undoUtil = gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document);
                    if (undoUtil != null)
                        RecordWireUndoEvent(undoUtil, "Rook: disconnect", new List<object> { targetInput });
                }
                catch { /* undo recording is best-effort */ }

                // Remove source
                var removeSourceMethod = targetInput.GetType().GetMethod("RemoveSource",
                    new[] { gh.Assembly!.GetType("Grasshopper.Kernel.IGH_Param")! });

                if (removeSourceMethod == null)
                    return new ApiResponse { Success = false, Data = "RemoveSource method not found" };

                var result = removeSourceMethod.Invoke(targetInput, new[] { sourceOutput });

                var expireMethod = targetObj.GetType().GetMethod("ExpireSolution", new[] { typeof(bool) });
                expireMethod?.Invoke(targetObj, new object[] { true });

                RefreshCanvas(gh.Canvas!);

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Disconnected = true,
                        Result = result,
                        Source = new
                        {
                            Guid = request.SourceGuid,
                            Param = resolvedSource.Name,
                            Index = resolvedSource.Index
                        },
                        Target = new
                        {
                            Guid = request.TargetGuid,
                            Param = resolvedTarget.Name,
                            Index = resolvedTarget.Index
                        }
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"DisconnectComponents failed: {ex.InnerException?.Message ?? ex.Message}"
                };
            }
        }

        #endregion

        #region Solution Control

        /// <summary>
        /// POST /gh/solve - Force recalculation of the solution
        /// Body: { delay?: number }
        /// </summary>
        internal ApiResponse TriggerSolve(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_solve");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_solve", null, gh.Error);

            int delay = 50;
            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    if (args?.TryGetValue("delay", out var d) == true)
                        delay = d.GetInt32();
                }
                catch { }
            }

            try
            {
                // Expire the document
                var expireMethod = gh.Document!.GetType().GetMethod("ExpireSolution");
                expireMethod?.Invoke(gh.Document, null);

                // Schedule solution
                var scheduleMethod = gh.Document.GetType().GetMethod("ScheduleSolution", new[] { typeof(int) });
                scheduleMethod?.Invoke(gh.Document, new object[] { delay });

                return new ApiResponse
                {
                    Success = true,
                    Data = new { Scheduled = true, Delay = delay }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"TriggerSolve failed: {ex.Message}"
                };
            }
        }

        #endregion

        #region Helper Methods

        private class GrasshopperContext
        {
            public bool Success { get; }
            public string? Error { get; }
            public Assembly? Assembly { get; }
            public object? Canvas { get; }
            public object? Document { get; }

            public GrasshopperContext(bool success, string? error, Assembly? assembly, object? canvas, object? document)
            {
                Success = success;
                Error = error;
                Assembly = assembly;
                Canvas = canvas;
                Document = document;
            }
        }

        private GrasshopperContext GetGrasshopper(bool requireDocument = true)
        {
            var dispatch = GrasshopperDispatchContext.Current;
            if (dispatch is not null)
            {
                return new GrasshopperContext(
                    true,
                    null,
                    dispatch.Assembly,
                    dispatch.Canvas,
                    dispatch.Document);
            }

            lock (_lock)
            {
                _ghAssembly ??= AppDomain.CurrentDomain.GetAssemblies()
                    .FirstOrDefault(a => a.GetName().Name == "Grasshopper");
            }

            if (_ghAssembly == null)
                return new GrasshopperContext(false, "Grasshopper assembly not found. Is Grasshopper open?", null, null, null);

            var instancesType = _ghAssembly.GetType("Grasshopper.Instances");
            if (instancesType == null)
                return new GrasshopperContext(false, "Grasshopper.Instances type not found", _ghAssembly, null, null);

            var activeCanvasProp = instancesType.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static);
            var canvas = activeCanvasProp?.GetValue(null);
            if (canvas == null)
                return new GrasshopperContext(false, "No active Grasshopper canvas", _ghAssembly, null, null);

            var documentProp = canvas.GetType().GetProperty("Document");
            var document = documentProp?.GetValue(canvas);

            if (document == null && requireDocument)
                return new GrasshopperContext(false, "No active Grasshopper document", _ghAssembly, canvas, null);

            return new GrasshopperContext(true, null, _ghAssembly, canvas, document);
        }

        private (bool Success, string? Error, object? Server) GetGrasshopperComponentServerNoCanvas()
        {
            Assembly? ghAssembly;
            lock (_lock)
            {
                _ghAssembly ??= AppDomain.CurrentDomain.GetAssemblies()
                    .FirstOrDefault(a => a.GetName().Name == "Grasshopper");
                ghAssembly = _ghAssembly;
            }

            if (ghAssembly == null)
                return (false, "Grasshopper assembly not found. Is Grasshopper open?", null);

            var instancesType = ghAssembly.GetType("Grasshopper.Instances");
            if (instancesType == null)
                return (false, "Grasshopper.Instances type not found", null);

            var serverProp = instancesType.GetProperty("ComponentServer", BindingFlags.Public | BindingFlags.Static);
            var server = serverProp?.GetValue(null);
            if (server == null)
                return (false, "ComponentServer not available", null);

            return (true, null, server);
        }

        private string? AddObjectToDocument(object document, object component)
        {
            var methods = document.GetType().GetMethods()
                .Where(m => m.Name == "AddObject")
                .ToList();

            // Find (IGH_DocumentObject, bool, int) overload
            var addMethod = methods.FirstOrDefault(m =>
            {
                var parms = m.GetParameters();
                return parms.Length == 3 &&
                       parms[0].ParameterType.IsAssignableFrom(component.GetType()) &&
                       parms[1].ParameterType == typeof(bool) &&
                       parms[2].ParameterType == typeof(int);
            });

            // Fallback to (IGH_DocumentObject, bool)
            addMethod ??= methods.FirstOrDefault(m =>
            {
                var parms = m.GetParameters();
                return parms.Length == 2 &&
                       parms[0].ParameterType.IsAssignableFrom(component.GetType()) &&
                       parms[1].ParameterType == typeof(bool);
            });

            if (addMethod == null)
                throw new InvalidOperationException("AddObject method not found on GH_Document");

            var paramCount = addMethod.GetParameters().Length;
            var addResult = paramCount == 3
                ? addMethod.Invoke(document, new object[] { component, true, -1 })
                : addMethod.Invoke(document, new object[] { component, true });
            if (addResult is not bool added)
                throw new InvalidOperationException("GH_Document.AddObject returned a non-Boolean result");
            if (!added)
                return null;

            // Return the GUID
            var guidProp = component.GetType().GetProperty("InstanceGuid");
            return guidProp?.GetValue(component)?.ToString();
        }

        private void RefreshCanvas(object canvas, bool scheduleSolution = true, int delayMs = 50)
        {
            if (scheduleSolution)
            {
                // Some callers only need a repaint after they have already queued a
                // document solve. Let them opt out so we do not stack an extra canvas
                // solve onto the same UI-thread callback.
                var scheduleMethod = canvas.GetType().GetMethod("ScheduleSolution", new[] { typeof(int) });
                scheduleMethod?.Invoke(canvas, new object[] { delayMs });
            }

            // Force visual redraw of the canvas
            var refreshMethod = canvas.GetType().GetMethod("Refresh");
            refreshMethod?.Invoke(canvas, null);
        }

        /// <summary>
        /// Get input and output params info for a component
        /// </summary>
        private object? GetComponentParams(object component)
        {
            try
            {
                // Check if it's a component with Params property
                var paramsProp = component.GetType().GetProperty("Params");
                if (paramsProp == null)
                {
                    // It might be a simple param object (like slider, panel)
                    // Check if it implements IGH_Param directly
                    var nicknameProp = component.GetType().GetProperty("NickName");
                    if (nicknameProp != null)
                    {
                        return new
                        {
                            IsSimpleParam = true,
                            NickName = nicknameProp.GetValue(component)?.ToString()
                        };
                    }
                    return null;
                }

                var paramsServer = paramsProp.GetValue(component);
                if (paramsServer == null) return null;

                var inputProp = paramsServer.GetType().GetProperty("Input");
                var outputProp = paramsServer.GetType().GetProperty("Output");

                var inputs = inputProp?.GetValue(paramsServer) as System.Collections.IEnumerable;
                var outputs = outputProp?.GetValue(paramsServer) as System.Collections.IEnumerable;

                var inputList = new List<object>();
                var outputList = new List<object>();

                if (inputs != null)
                {
                    int idx = 0;
                    foreach (var input in inputs)
                    {
                        inputList.Add(new
                        {
                            Index = idx++,
                            Name = input.GetType().GetProperty("Name")?.GetValue(input)?.ToString(),
                            NickName = input.GetType().GetProperty("NickName")?.GetValue(input)?.ToString(),
                            TypeName = input.GetType().GetProperty("TypeName")?.GetValue(input)?.ToString(),
                            Access = GetParamAccessString(input),
                            Optional = GetParamOptionalFlag(input),
                            Description = input.GetType().GetProperty("Description")?.GetValue(input)?.ToString(),
                            Hidden = input.GetType().GetProperty("Hidden")?.GetValue(input) is bool hidden && hidden,
                            SourceCount = (input.GetType().GetProperty("SourceCount")?.GetValue(input) as int?) ?? 0
                        });
                    }
                }

                if (outputs != null)
                {
                    int idx = 0;
                    foreach (var output in outputs)
                    {
                        outputList.Add(new
                        {
                            Index = idx++,
                            Name = output.GetType().GetProperty("Name")?.GetValue(output)?.ToString(),
                            NickName = output.GetType().GetProperty("NickName")?.GetValue(output)?.ToString(),
                            TypeName = output.GetType().GetProperty("TypeName")?.GetValue(output)?.ToString(),
                            Access = GetParamAccessString(output),
                            Optional = GetParamOptionalFlag(output),
                            Description = output.GetType().GetProperty("Description")?.GetValue(output)?.ToString(),
                            Hidden = output.GetType().GetProperty("Hidden")?.GetValue(output) is bool hidden && hidden,
                            RecipientCount = (output.GetType().GetProperty("Recipients")?.GetValue(output) as System.Collections.IEnumerable)?.Cast<object>().Count() ?? 0
                        });
                    }
                }

                return new
                {
                    Inputs = inputList,
                    Outputs = outputList
                };
            }
            catch
            {
                return null;
            }
        }

        /// <summary>
        /// Get runtime messages (warnings, errors) from a component
        /// </summary>
        private object? GetRuntimeMessages(object component, bool debug = false)
        {
            var debugInfo = new List<string>();
            try
            {
                // Try to find RuntimeMessages method - check all methods with that name
                var allMethods = component.GetType().GetMethods()
                    .Where(m => m.Name.Contains("Runtime") || m.Name.Contains("Message"))
                    .Select(m => $"{m.Name}({string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name))})")
                    .ToList();

                if (debug)
                    debugInfo.Add($"Methods found: {string.Join("; ", allMethods)}");

                var messagesMethod = component.GetType().GetMethod("RuntimeMessages");
                if (messagesMethod == null)
                {
                    if (debug)
                        debugInfo.Add("RuntimeMessages method not found");

                    // Return debug info if requested
                    if (debug && debugInfo.Count > 0)
                        return new { Debug = debugInfo, Warnings = new List<string>(), Errors = new List<string>() };
                    return null;
                }

                // Get the enum type from the method's parameter
                var paramInfo = messagesMethod.GetParameters();
                if (paramInfo.Length == 0)
                {
                    if (debug)
                        debugInfo.Add("RuntimeMessages has no parameters");
                    return null;
                }
                var enumType = paramInfo[0].ParameterType;
                if (debug)
                    debugInfo.Add($"Enum type: {enumType.FullName}");

                var warnings = new List<string>();
                var errors = new List<string>();

                // Check RuntimeMessageLevel property to see component state
                if (debug)
                {
                    var levelProp = component.GetType().GetProperty("RuntimeMessageLevel");
                    if (levelProp != null)
                    {
                        var level = levelProp.GetValue(component);
                        debugInfo.Add($"RuntimeMessageLevel property: {level} (int: {Convert.ToInt32(level)})");
                    }
                }

                // GH_RuntimeMessageLevel enum: Blank=0, Remark=1, Warning=10, Error=20
                // Try to get Warning level (10 = orange)
                try
                {
                    var warningLevel = Enum.ToObject(enumType, 10);
                    var warningResult = messagesMethod.Invoke(component, new object[] { warningLevel });
                    if (debug)
                        debugInfo.Add($"Warning result type: {warningResult?.GetType().FullName ?? "null"}");

                    var warningMessages = warningResult as System.Collections.IEnumerable;
                    if (warningMessages != null)
                    {
                        foreach (var msg in warningMessages)
                            warnings.Add(msg?.ToString() ?? "");
                    }
                    if (debug)
                        debugInfo.Add($"Warnings retrieved: {warnings.Count}");
                }
                catch (Exception ex)
                {
                    if (debug)
                        debugInfo.Add($"Warning retrieval error: {ex.Message}");
                }

                // Try to get Error level (20 = red)
                try
                {
                    var errorLevel = Enum.ToObject(enumType, 20);
                    var errorResult = messagesMethod.Invoke(component, new object[] { errorLevel });
                    if (debug)
                        debugInfo.Add($"Error result type: {errorResult?.GetType().FullName ?? "null"}");

                    var errorMessages = errorResult as System.Collections.IEnumerable;
                    if (errorMessages != null)
                    {
                        foreach (var msg in errorMessages)
                            errors.Add(msg?.ToString() ?? "");
                    }
                    if (debug)
                        debugInfo.Add($"Errors retrieved: {errors.Count}");
                }
                catch (Exception ex)
                {
                    if (debug)
                        debugInfo.Add($"Error retrieval error: {ex.Message}");
                }

                if (warnings.Count == 0 && errors.Count == 0 && !debug)
                    return null;

                if (debug)
                {
                    return new
                    {
                        Debug = debugInfo,
                        Warnings = warnings,
                        Errors = errors
                    };
                }

                return new
                {
                    Warnings = warnings,
                    Errors = errors
                };
            }
            catch (Exception ex)
            {
                if (debug)
                    return new { Debug = new List<string> { $"Exception: {ex.Message}" }, Warnings = new List<string>(), Errors = new List<string>() };
                return null;
            }
        }

        /// <summary>
        /// Get a param from a component by index or name.
        /// isInput=true for input params, false for output params.
        /// </summary>
        private object? GetParam(object component, bool isInput, int? index, string? name)
        {
            try
            {
                // Check if component is itself a param (like GH_NumberSlider)
                var paramsProp = component.GetType().GetProperty("Params");

                if (paramsProp == null)
                {
                    // Component might BE a param (slider, panel, etc.)
                    // For output (isInput=false), return the component itself if it's a param
                    // For input, check if it has Sources property
                    if (!isInput)
                    {
                        // Check if it implements IGH_Param by looking for Recipients property
                        if (component.GetType().GetProperty("Recipients") != null)
                            return component;
                    }
                    else
                    {
                        // For input, check if it has Sources property
                        if (component.GetType().GetProperty("Sources") != null)
                            return component;
                    }
                    return null;
                }

                var paramsServer = paramsProp.GetValue(component);
                if (paramsServer == null) return null;

                var listProp = isInput
                    ? paramsServer.GetType().GetProperty("Input")
                    : paramsServer.GetType().GetProperty("Output");

                var list = listProp?.GetValue(paramsServer) as System.Collections.IEnumerable;
                if (list == null) return null;

                var paramList = list.Cast<object>().ToList();

                if (index.HasValue && index.Value >= 0 && index.Value < paramList.Count)
                {
                    return paramList[index.Value];
                }

                if (!string.IsNullOrEmpty(name))
                {
                    var nameLower = name.ToLowerInvariant();
                    foreach (var p in paramList)
                    {
                        var pName = p.GetType().GetProperty("Name")?.GetValue(p)?.ToString()?.ToLowerInvariant();
                        var pNickname = p.GetType().GetProperty("NickName")?.GetValue(p)?.ToString()?.ToLowerInvariant();
                        if (pName == nameLower || pNickname == nameLower)
                            return p;
                    }
                }

                // If no specific param requested, return first one
                if (!index.HasValue && string.IsNullOrEmpty(name) && paramList.Count > 0)
                    return paramList[0];

                return null;
            }
            catch
            {
                return null;
            }
        }

        #endregion

        #region Batch Component Info

        /// <summary>
        /// POST /gh/batch-component-info - Resolve names or GUIDs to source-specific metadata and I/O.
        /// Body admits exactly one nonempty selector family: names or guids.
        /// </summary>
        public ApiResponse HandleBatchComponentInfo(string? body)
        {
            var componentServer = GetGrasshopperComponentServerNoCanvas();
            if (!componentServer.Success)
                return new ApiResponse { Success = false, Data = componentServer.Error };

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            return HandleBatchComponentInfoFromServer(
                componentServer.Server!,
                body!,
                CreateGrasshopperUserObject);
        }

        internal ApiResponse HandleBatchComponentInfoFromServer(
            object server,
            string body,
            Func<string, object>? userObjectFactory = null)
        {
            if (!TryReadMetadataSelectors(body, out var selectorKind, out var selectors, out var requestError))
                return new ApiResponse { Success = false, Data = requestError };

            try
            {
                var proxySnapshot = ReadObjectProxySnapshot(server);
                var results = new List<Dictionary<string, object?>>();
                foreach (var selectorValue in selectors)
                {
                    var selector = MetadataSelector(selectorKind, selectorValue);
                    if (selectorKind == "guid")
                    {
                        if (!Guid.TryParse(selectorValue, out var guid))
                        {
                            results.Add(MetadataFailure(selector, "invalid_guid", "invalid_guid"));
                            continue;
                        }

                        var canonicalGuid = guid.ToString("D").ToLowerInvariant();
                        object? proxy = null;
                        var duplicateGuid = false;
                        var incompleteGuidScan = false;
                        foreach (var candidateProxy in proxySnapshot)
                        {
                            try
                            {
                                var guidValue = RequireHostProperty(candidateProxy, "Guid");
                                if (guidValue is not Guid candidateGuid)
                                    throw new InvalidOperationException("Proxy Guid was not a GUID.");
                                if (candidateGuid != guid)
                                    continue;
                                if (proxy != null)
                                    duplicateGuid = true;
                                else
                                    proxy = candidateProxy;
                            }
                            catch
                            {
                                incompleteGuidScan = true;
                            }
                        }

                        if (duplicateGuid || (proxy == null && incompleteGuidScan))
                        {
                            results.Add(MetadataFailure(
                                selector,
                                "projection_failure",
                                "proxy_projection_failed",
                                canonicalGuid));
                            continue;
                        }

                        if (proxy == null)
                        {
                            results.Add(MetadataFailure(
                                selector,
                                "not_found",
                                "component_not_found",
                                canonicalGuid));
                            continue;
                        }

                        results.Add(ProjectSelectedMetadata(
                            server,
                            selector,
                            canonicalGuid,
                            proxy,
                            userObjectFactory));
                        continue;
                    }

                    var matches = new List<object>();
                    var incompleteNameScan = false;
                    foreach (var proxy in proxySnapshot)
                    {
                        object desc;
                        string name;
                        try
                        {
                            desc = RequireHostProperty(proxy, "Desc")
                                ?? throw new InvalidOperationException("Proxy Desc was null.");
                            name = RequireHostString(desc, "Name");
                        }
                        catch
                        {
                            incompleteNameScan = true;
                            continue;
                        }

                        if (!string.Equals(name, selectorValue, StringComparison.OrdinalIgnoreCase))
                            continue;

                        try
                        {
                            var obsolete = RequireHostProperty(proxy, "Obsolete");
                            if (obsolete is not bool obsoleteValue)
                                throw new InvalidOperationException("Proxy Obsolete was not boolean.");
                            if (obsoleteValue)
                                continue;
                            var exposure = ReadExposure(proxy);
                            if ((exposure & 16) == 0)
                                matches.Add(proxy);
                        }
                        catch
                        {
                            incompleteNameScan = true;
                        }
                    }

                    if (incompleteNameScan)
                    {
                        results.Add(MetadataFailure(
                            selector,
                            "projection_failure",
                            "proxy_projection_failed"));
                        continue;
                    }

                    if (matches.Count == 0)
                    {
                        results.Add(MetadataFailure(selector, "not_found", "component_not_found"));
                        continue;
                    }

                    if (matches.Count > 1)
                    {
                        try
                        {
                            var candidates = matches
                                .Select(proxy => ProjectLibraryCandidate(proxy, null, "exact_name"))
                                .ToList();
                            SortMetadataCandidates(server, candidates);
                            var failure = MetadataFailure(selector, "ambiguous_name", error: null);
                            failure["candidates"] = candidates
                                .Select(candidate => CandidatePayload(
                                    candidate,
                                    CandidatePayloadShape.Ambiguity))
                                .ToList();
                            results.Add(failure);
                        }
                        catch
                        {
                            results.Add(MetadataFailure(selector, "projection_failure", "proxy_projection_failed"));
                        }
                        continue;
                    }

                    var selected = matches[0];
                    try
                    {
                        var guidValue = RequireHostProperty(selected, "Guid");
                        if (guidValue is not Guid selectedGuid)
                            throw new InvalidOperationException("Proxy Guid was not a GUID.");
                        results.Add(ProjectSelectedMetadata(
                            server,
                            selector,
                            selectedGuid.ToString("D").ToLowerInvariant(),
                            selected,
                            userObjectFactory));
                    }
                    catch
                    {
                        results.Add(MetadataFailure(selector, "projection_failure", "proxy_projection_failed"));
                    }
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        Count = results.Count,
                        Errors = results.Count(result => !Equals(result["status"], "success")),
                        Results = results
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"BatchComponentInfo failed: {UnwrapInvocationException(ex).Message}"
                };
            }
        }

        private static bool TryReadMetadataSelectors(
            string body,
            out string selectorKind,
            out List<string> selectors,
            out string error)
        {
            selectorKind = "";
            selectors = new List<string>();
            error = "Invalid selector request";
            try
            {
                using var document = JsonDocument.Parse(body);
                if (document.RootElement.ValueKind != JsonValueKind.Object)
                    return false;

                var hasNames = document.RootElement.TryGetProperty("names", out var names);
                var hasGuids = document.RootElement.TryGetProperty("guids", out var guids);
                if (hasNames == hasGuids)
                    return false;

                var selected = hasNames ? names : guids;
                if (selected.ValueKind != JsonValueKind.Array || selected.GetArrayLength() == 0)
                    return false;

                foreach (var item in selected.EnumerateArray())
                {
                    if (item.ValueKind != JsonValueKind.String)
                        return false;
                    selectors.Add(item.GetString()!);
                }

                selectorKind = hasNames ? "name" : "guid";
                error = "";
                return true;
            }
            catch
            {
                error = "Invalid JSON body";
                return false;
            }
        }

        private Dictionary<string, object?> ProjectSelectedMetadata(
            object server,
            Dictionary<string, object?> selector,
            string canonicalGuid,
            object proxy,
            Func<string, object>? userObjectFactory)
        {
            LibraryCandidate candidate;
            try
            {
                candidate = ProjectLibraryCandidate(proxy, null, null);
            }
            catch
            {
                return MetadataFailure(selector, "projection_failure", "proxy_projection_failed", canonicalGuid);
            }

            var result = MetadataPrefix(selector, candidate);
            object provenance;
            object? userObject = null;
            try
            {
                if (candidate.SourceKind == "compiled")
                {
                    provenance = ProjectCompiledProvenance(server, proxy);
                }
                else
                {
                    var projection = ProjectUserObjectProvenance(proxy, userObjectFactory);
                    provenance = projection.Provenance;
                    userObject = projection.UserObject;
                }
            }
            catch
            {
                result["status"] = "projection_failure";
                result["error"] = "provenance_projection_failed";
                return result;
            }

            result["provenance"] = provenance;

            object component;
            try
            {
                var createInstance = RequireHostMethod(proxy.GetType(), "CreateInstance", 0);
                component = createInstance.Invoke(proxy, null)
                    ?? throw new InvalidOperationException("CreateInstance returned null.");
            }
            catch
            {
                result["status"] = "instantiation_failure";
                result["error"] = "component_instantiation_failed";
                return result;
            }

            try
            {
                result["implementation"] = ProjectImplementation(component, candidate.SourceKind, userObject);
            }
            catch
            {
                result["status"] = "projection_failure";
                result["error"] = "implementation_projection_failed";
                return result;
            }

            result["params"] = GetComponentParams(component);
            result["status"] = "success";
            return result;
        }

        private static object ProjectCompiledProvenance(object server, object proxy)
        {
            var libraryGuidValue = RequireHostProperty(proxy, "LibraryGuid");
            if (libraryGuidValue is not Guid libraryGuid)
                throw new InvalidOperationException("Proxy LibraryGuid was not a GUID.");
            var findAssembly = server.GetType().GetMethod(
                "FindAssembly",
                BindingFlags.Public | BindingFlags.Instance,
                binder: null,
                types: new[] { typeof(Guid) },
                modifiers: null)
                ?? throw new InvalidOperationException("FindAssembly(Guid) was missing.");
            var info = findAssembly.Invoke(server, new object[] { libraryGuid })
                ?? throw new InvalidOperationException("FindAssembly(Guid) returned null.");
            var assemblyValue = RequireHostProperty(info, "Assembly");
            if (assemblyValue != null && assemblyValue is not Assembly)
                throw new InvalidOperationException("Assembly was not a CLR assembly or null.");

            return new
            {
                LibraryGuid = libraryGuid.ToString("D").ToLowerInvariant(),
                LibraryName = ReadNullableHostString(info, "Name"),
                LibraryVersion = ReadNullableHostString(info, "Version"),
                AssemblyFullName = ((Assembly?)assemblyValue)?.FullName,
                AssemblyVersion = ReadNullableHostString(info, "AssemblyVersion"),
                AssemblyLocation = ReadNullableHostString(info, "Location")
            };
        }

        private static UserObjectProjection ProjectUserObjectProvenance(
            object proxy,
            Func<string, object>? userObjectFactory)
        {
            var location = RequireHostString(proxy, "Location");
            var userObject = (userObjectFactory ?? throw new InvalidOperationException("User-object factory unavailable."))(location)
                ?? throw new InvalidOperationException("User-object construction returned null.");
            var path = RequireHostString(userObject, "Path");
            if (!string.Equals(
                NormalizeWindowsPath(location),
                NormalizeWindowsPath(path),
                StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("User-object path did not match its selected proxy.");
            }

            var data = RequireHostProperty(userObject, "Data");
            long? byteLength = null;
            string? sha256 = null;
            if (data != null)
            {
                if (data is not byte[] bytes)
                    throw new InvalidOperationException("User-object Data was not byte[] or null.");
                using var hash = SHA256.Create();
                byteLength = bytes.LongLength;
                sha256 = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "");
            }

            return new UserObjectProjection
            {
                UserObject = userObject,
                Provenance = new
                {
                    Path = path,
                    ContentByteLength = byteLength,
                    ContentSha256 = sha256
                }
            };
        }

        private static string NormalizeWindowsPath(string path) =>
            Path.GetFullPath(path).Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar);

        private static object ProjectImplementation(object component, string sourceKind, object? userObject)
        {
            var componentGuidValue = RequireHostProperty(component, "ComponentGuid");
            if (componentGuidValue is not Guid componentGuid)
                throw new InvalidOperationException("ComponentGuid was not a GUID.");
            var type = component.GetType();
            var runtimeType = type.FullName
                ?? throw new InvalidOperationException("Runtime type FullName was null.");
            var assembly = type.Assembly;
            var assemblyName = assembly.GetName();
            string? baseGuid = null;
            if (sourceKind == "user_object")
            {
                var baseGuidValue = RequireHostProperty(
                    userObject ?? throw new InvalidOperationException("User object was missing."),
                    "BaseGuid");
                if (baseGuidValue is not Guid parsedBaseGuid)
                    throw new InvalidOperationException("User-object BaseGuid was not a GUID.");
                baseGuid = parsedBaseGuid.ToString("D").ToLowerInvariant();
            }

            return new
            {
                BaseGuid = baseGuid,
                ComponentGuid = componentGuid.ToString("D").ToLowerInvariant(),
                RuntimeType = runtimeType,
                RuntimeAssemblyName = assemblyName.Name,
                RuntimeAssemblyVersion = assemblyName.Version?.ToString(),
                RuntimeAssemblyLocation = assembly.Location
            };
        }

        private object CreateGrasshopperUserObject(string path)
        {
            var type = _ghAssembly?.GetType("Grasshopper.Kernel.GH_UserObject")
                ?? throw new InvalidOperationException("Grasshopper GH_UserObject type was unavailable.");
            var constructor = type.GetConstructor(new[] { typeof(string) })
                ?? throw new InvalidOperationException("GH_UserObject(string) constructor was unavailable.");
            return constructor.Invoke(new object[] { path });
        }

        private static Dictionary<string, object?> MetadataSelector(string kind, string value) =>
            new()
            {
                ["kind"] = kind,
                ["value"] = value
            };

        private static Dictionary<string, object?> MetadataFailure(
            Dictionary<string, object?> selector,
            string status,
            string? error,
            string? guid = null)
        {
            var result = new Dictionary<string, object?>
            {
                ["selector"] = selector,
                ["status"] = status
            };
            if (guid != null)
                result["guid"] = guid;
            if (error != null)
                result["error"] = error;
            return result;
        }

        private static Dictionary<string, object?> MetadataPrefix(
            Dictionary<string, object?> selector,
            LibraryCandidate candidate) =>
            new()
            {
                ["selector"] = selector,
                ["status"] = "projection_failure",
                ["guid"] = candidate.Guid,
                ["name"] = candidate.Name,
                ["nickName"] = candidate.NickName,
                ["description"] = candidate.Description,
                ["category"] = candidate.Category,
                ["subCategory"] = candidate.SubCategory,
                ["sourceKind"] = candidate.SourceKind
            };

        private static void SortMetadataCandidates(object server, List<LibraryCandidate> candidates)
        {
            var compareProxies = RequireHostMethod(server.GetType(), "CompareProxies", 2);
            candidates.Sort((left, right) =>
            {
                var comparisonValue = compareProxies.Invoke(server, new[] { left.Proxy, right.Proxy });
                if (comparisonValue is not int comparison)
                    throw new InvalidOperationException("CompareProxies returned a non-integer result.");
                return comparison != 0
                    ? comparison
                    : StringComparer.Ordinal.Compare(left.Guid, right.Guid);
            });
        }

        private sealed class UserObjectProjection
        {
            public object UserObject { get; init; } = null!;
            public object Provenance { get; init; } = null!;
        }

        #endregion

        #region Canvas Graph Protocol

        /// <summary>
        /// POST /gh/snapshot - Get the complete canvas state as a structured document.
        /// Returns all components, connections (as flow strings), groups, and diagnostics.
        /// </summary>
        public ApiResponse TakeSnapshot(string? body)
        {
            bool includeData = true;
            int maxPreviewItems = 3;
            string? readinessReceiptId = null;
            var fenced = false;
            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    using var document = JsonDocument.Parse(body);
                    if (document.RootElement.ValueKind != JsonValueKind.Object)
                        return new ApiResponse { Success = false, Data = "Invalid gh_snapshot request body" };

                    var json = document.RootElement;
                    fenced = json.TryGetProperty("readiness_receipt_id", out var receiptElement);
                    if (fenced)
                    {
                        if (receiptElement.ValueKind != JsonValueKind.String)
                            return ReadinessIssueFailure("readiness_receipt_id_invalid");
                        readinessReceiptId = receiptElement.GetString();
                        if (string.IsNullOrWhiteSpace(readinessReceiptId))
                            return ReadinessIssueFailure("readiness_receipt_id_invalid");

                        if (!json.TryGetProperty("include_data", out var fencedIncludeData) ||
                            fencedIncludeData.ValueKind != JsonValueKind.True)
                        {
                            return ReadinessIssueFailure("readiness_snapshot_request_invalid");
                        }
                        includeData = true;

                        if (!json.TryGetProperty("max_preview_items", out var fencedMaxPreview) ||
                            fencedMaxPreview.ValueKind != JsonValueKind.Number ||
                            !fencedMaxPreview.TryGetInt32(out maxPreviewItems) ||
                            maxPreviewItems < 1 ||
                            maxPreviewItems > 1000)
                        {
                            return ReadinessIssueFailure("readiness_snapshot_request_invalid");
                        }
                    }
                    else
                    {
                        if (json.TryGetProperty("include_data", out var incData) &&
                            incData.ValueKind is JsonValueKind.True or JsonValueKind.False)
                        {
                            includeData = incData.GetBoolean();
                        }
                        if (json.TryGetProperty("max_preview_items", out var maxPrev) &&
                            maxPrev.ValueKind == JsonValueKind.Number &&
                            maxPrev.TryGetInt32(out var legacyMaxPreview))
                        {
                            maxPreviewItems = legacyMaxPreview;
                        }
                    }
                }
                catch (JsonException)
                {
                    return new ApiResponse { Success = false, Data = "Invalid gh_snapshot request body" };
                }
            }

            GrasshopperContext gh;
            GhFencedReadGate? readinessGate = null;
            if (fenced)
            {
                gh = GetGrasshopper();
                if (!gh.Success)
                    return GrasshopperNotReadyResponse("gh_snapshot", null, gh.Error);

                var gate = _solveReceiptRegistry.CheckFencedRead(
                    readinessReceiptId!,
                    gh.Document!,
                    GrasshopperDispatchContext.Current?.DocumentId.ToString("D"));
                if (!gate.Allowed)
                    return ReadinessFenceFailure(gate);
                readinessGate = gate;

                var notReady = EnsureGrasshopperReadyForEdit("gh_snapshot");
                if (notReady != null)
                    return notReady;
            }
            else
            {
                var notReady = EnsureGrasshopperReadyForEdit("gh_snapshot");
                if (notReady != null)
                    return notReady;

                gh = GetGrasshopper();
                if (!gh.Success)
                    return GrasshopperNotReadyResponse("gh_snapshot", null, gh.Error);
            }

            try
            {
                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var objects = (objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable)?
                    .Cast<object>().ToList() ?? new List<object>();

                // Resolve GH types
                var groupType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Group");
                var relayType = gh.Assembly.GetType("Grasshopper.Kernel.Special.GH_Relay");

                // Phase 1: Build ID registry from all objects
                var objectGuids = new List<(Guid guid, bool isGroup)>();
                var guidToObj = new Dictionary<Guid, object>();
                foreach (var obj in objects)
                {
                    try
                    {
                        var guid = (Guid)obj.GetType().GetProperty("InstanceGuid")!.GetValue(obj)!;
                        bool isGroup = groupType?.IsInstanceOfType(obj) ?? false;
                        objectGuids.Add((guid, isGroup));
                        guidToObj[guid] = obj;
                    }
                    catch
                    {
                        // Skip objects with inaccessible InstanceGuid (corrupted, placeholder, etc.)
                    }
                }
                var epoch = _idRegistry.Rebuild(objectGuids);

                // Phase 2: Single pass — classify objects, extract components, groups, relays
                var components = new List<object>();
                var flows = new List<string>();
                var groups = new List<object>();
                var relayIds = new List<string>();
                var errorIds = new List<string>();
                var warningIds = new List<string>();
                int errorCount = 0;
                int warningCount = 0;
                var behavioralPointOutputs = fenced ? new List<object>() : null;

                // Build a set of relay GUIDs for flow traversal
                var relayGuids = new HashSet<Guid>();
                foreach (var obj in objects)
                {
                    try
                    {
                        if (relayType?.IsInstanceOfType(obj) == true)
                        {
                            var guid = (Guid)obj.GetType().GetProperty("InstanceGuid")!.GetValue(obj)!;
                            relayGuids.Add(guid);
                        }
                    }
                    catch
                    {
                        // Skip objects with inaccessible InstanceGuid
                    }
                }

                foreach (var obj in objects)
                {
                    // Per-component try/catch: one broken component must not kill the entire snapshot
                    string? shortId = null;
                    try
                    {
                        var instanceGuid = (Guid)obj.GetType().GetProperty("InstanceGuid")!.GetValue(obj)!;
                        shortId = _idRegistry.ResolveReverse(instanceGuid);
                        if (shortId == null) continue;

                        var typeName = obj.GetType().Name;

                        // Skip wire display objects
                        if (typeName.Contains("Wire")) continue;

                        // Handle groups
                        if (groupType?.IsInstanceOfType(obj) == true)
                        {
                            var groupEntry = BuildGroupEntry(obj, shortId);
                            if (groupEntry != null) groups.Add(groupEntry);
                            continue;
                        }

                        // Handle relays — track but don't include as components
                        if (relayType?.IsInstanceOfType(obj) == true)
                        {
                            relayIds.Add(shortId);
                            continue;
                        }

                        // Handle placeholder components (from missing plugins)
                        if (typeName == "GH_PlaceholderComponent")
                        {
                            var phName = obj.GetType().GetProperty("Name")?.GetValue(obj)?.ToString();
                            float[]? phPos = GetPosition(obj);
                            var phEntry = new Dictionary<string, object?>
                            {
                                ["id"] = shortId,
                                ["type"] = "PlaceholderComponent",
                                ["name"] = phName ?? "Unknown",
                                ["pos"] = phPos,
                                ["is_placeholder"] = true,
                                ["errors"] = new List<string> { "Missing plugin: component is a placeholder" }
                            };
                            components.Add(phEntry);
                            errorIds.Add(shortId);
                            errorCount++;
                            // Still extract flows — GH preserves wiring on placeholders
                            ExtractComponentFlows(obj, shortId, guidToObj, relayGuids, flows);
                            continue;
                        }

                        // Handle Scribble annotations — capture their text content
                        if (typeName == "GH_Scribble")
                        {
                            var scribbleText = obj.GetType().GetProperty("Text")?.GetValue(obj)?.ToString();
                            var scribbleEntry = new Dictionary<string, object?>
                            {
                                ["id"] = shortId,
                                ["type"] = "Scribble",
                                ["nick"] = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString(),
                                ["pos"] = GetPosition(obj),
                                ["is_annotation"] = true,
                                ["text"] = scribbleText ?? ""
                            };
                            components.Add(scribbleEntry);
                            continue;
                        }

                        // Handle Markup (Sketch) annotations
                        if (typeName == "GH_Markup")
                        {
                            var markupText = obj.GetType().GetProperty("Text")?.GetValue(obj)?.ToString();
                            var markupEntry = new Dictionary<string, object?>
                            {
                                ["id"] = shortId,
                                ["type"] = "Markup",
                                ["nick"] = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString(),
                                ["pos"] = GetPosition(obj),
                                ["is_annotation"] = true,
                                ["text"] = markupText ?? ""
                            };
                            components.Add(markupEntry);
                            continue;
                        }

                        // Determine if this is a simple param (slider, panel, toggle, value list)
                        bool isSimpleParam = IsSimpleParam(typeName);

                        // Extract position
                        float[]? pos = GetPosition(obj);

                        // Extract runtime messages
                        var msgs = GetRuntimeMessages(obj);
                        var errors = new List<string>();
                        var warnings = new List<string>();
                        if (msgs != null)
                        {
                            // msgs is anonymous type with Warnings and Errors
                            var msgType = msgs.GetType();
                            var warnProp = msgType.GetProperty("Warnings");
                            var errProp = msgType.GetProperty("Errors");
                            if (warnProp?.GetValue(msgs) is List<string> w) warnings = w;
                            if (errProp?.GetValue(msgs) is List<string> e) errors = e;
                        }

                        if (errors.Count > 0) { errorIds.Add(shortId); errorCount += errors.Count; }
                        if (warnings.Count > 0) { warningIds.Add(shortId); warningCount += warnings.Count; }

                        if (isSimpleParam)
                        {
                            // Build simple param entry (slider, panel, toggle, value list)
                            var entry = BuildSimpleParamEntry(obj, shortId, typeName, pos, errors, warnings);
                            if (entry != null) components.Add(entry);

                            // Extract flows for simple params with Sources (receiving data)
                            ExtractSimpleParamFlows(obj, shortId, instanceGuid, guidToObj, relayGuids, flows);
                        }
                        else
                        {
                            // Build regular component entry
                            var entry = BuildComponentEntry(
                                obj,
                                shortId,
                                typeName,
                                pos,
                                errors,
                                warnings,
                                includeData,
                                maxPreviewItems,
                                behavioralPointOutputs);
                            if (entry != null) components.Add(entry);

                            // Extract flows from this component's input params
                            ExtractComponentFlows(obj, shortId, guidToObj, relayGuids, flows);
                        }
                    }
                    catch (Exception ex)
                    {
                        // Emit a degraded entry so the component is visible but marked as broken
                        var fallbackId = shortId ?? "C?";
                        var fallbackName = "Unknown";
                        try { fallbackName = obj.GetType().GetProperty("Name")?.GetValue(obj)?.ToString() ?? obj.GetType().Name; } catch { }
                        float[]? fallbackPos = null;
                        try { fallbackPos = GetPosition(obj); } catch { }
                        components.Add(new Dictionary<string, object?>
                        {
                            ["id"] = fallbackId,
                            ["type"] = "BROKEN",
                            ["name"] = fallbackName,
                            ["pos"] = fallbackPos,
                            ["errors"] = new List<string> { $"Snapshot error: {ex.Message}" }
                        });
                        errorIds.Add(fallbackId);
                        errorCount++;
                    }
                }

                // Build document info
                string? docName = null, docPath = null;
                try
                {
                    docName = gh.Document.GetType().GetProperty("DisplayName")?.GetValue(gh.Document)?.ToString();
                    docPath = gh.Document.GetType().GetProperty("FilePath")?.GetValue(gh.Document)?.ToString();
                }
                catch { }

                var snapshot = new Dictionary<string, object?>
                {
                    ["version"] = "1.0.0",
                    ["document"] = new { name = docName ?? "untitled", path = docPath ?? "" },
                    ["epoch"] = epoch,
                    ["components"] = components,
                    ["flows"] = flows
                };

                if (groups.Count > 0)
                    snapshot["groups"] = groups;

                if (relayIds.Count > 0)
                    snapshot["relays"] = relayIds;

                snapshot["diagnostics"] = new
                {
                    total = components.Count,
                    errors = errorCount,
                    warnings = warningCount,
                    error_ids = errorIds.Count > 0 ? errorIds : null,
                    warning_ids = warningIds.Count > 0 ? warningIds : null
                };

                if (readinessGate?.Receipt is GhSolveReadinessReceipt receipt)
                {
                    snapshot["readiness_fence"] = receipt.GhDocumentId is null
                        ? (object)new
                        {
                            readiness_receipt_id = receipt.ReceiptId,
                            document_session_id = receipt.DocumentSessionId,
                            mutation_epoch = receipt.MutationEpoch,
                            solution_run_epoch = receipt.SolutionRunEpoch,
                            completed_solution_run_epoch = receipt.CompletedSolutionRunEpoch,
                        }
                        : new
                        {
                            readiness_receipt_id = receipt.ReceiptId,
                            document_session_id = receipt.DocumentSessionId,
                            mutation_epoch = receipt.MutationEpoch,
                            solution_run_epoch = receipt.SolutionRunEpoch,
                            completed_solution_run_epoch = receipt.CompletedSolutionRunEpoch,
                            gh_document_id = receipt.GhDocumentId,
                        };
                    snapshot["behavioral_point_outputs"] = behavioralPointOutputs!;
                }

                return new ApiResponse { Success = true, Data = snapshot };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"TakeSnapshot failed: {ex.Message}" };
            }
        }

        private ApiResponse TakeStructuralSnapshot()
        {
            return TakeSnapshot("{\"include_data\":false,\"max_preview_items\":0}");
        }

        private bool IsSimpleParam(string typeName)
        {
            return typeName is "GH_NumberSlider" or "GH_Panel" or "GH_BooleanToggle"
                or "GH_ValueList" or "GH_ColourSwatch" or "GH_MultiDimensionalSlider";
        }

        private float[]? GetPosition(object obj)
        {
            try
            {
                var attr = obj.GetType().GetProperty("Attributes")?.GetValue(obj);
                if (attr == null) return null;
                var pivot = attr.GetType().GetProperty("Pivot")?.GetValue(attr);
                if (pivot is PointF pf)
                    return new[] { (float)Math.Round(pf.X, 1), (float)Math.Round(pf.Y, 1) };
            }
            catch { }
            return null;
        }

        private object? BuildSimpleParamEntry(object obj, string shortId, string typeName,
            float[]? pos, List<string> errors, List<string> warnings)
        {
            var name = obj.GetType().GetProperty("Name")?.GetValue(obj)?.ToString();
            var nick = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString();

            // Clean type name: strip "GH_" prefix for readability
            var cleanType = typeName.StartsWith("GH_") ? typeName.Substring(3) : typeName;

            var entry = new Dictionary<string, object?>
            {
                ["id"] = shortId,
                ["type"] = cleanType,
                ["nick"] = nick ?? name,
                ["pos"] = pos,
                ["is_param"] = true
            };

            // Extract value based on type
            var value = ExtractParamValue(obj, typeName);
            if (value != null)
                entry["value"] = value;

            if (errors.Count > 0) entry["errors"] = errors;
            if (warnings.Count > 0) entry["warnings"] = warnings;

            return entry;
        }

        private object? ExtractParamValue(object obj, string typeName)
        {
            try
            {
                switch (typeName)
                {
                    case "GH_NumberSlider":
                    {
                        var slider = obj.GetType().GetProperty("Slider")?.GetValue(obj);
                        if (slider == null) return null;
                        var val = slider.GetType().GetProperty("Value")?.GetValue(slider);
                        var min = slider.GetType().GetProperty("Minimum")?.GetValue(slider);
                        var max = slider.GetType().GetProperty("Maximum")?.GetValue(slider);
                        return new { type = "slider", val, min, max };
                    }
                    case "GH_Panel":
                    {
                        var content = obj.GetType().GetProperty("UserText")?.GetValue(obj)?.ToString() ?? "";
                        return new { type = "panel", val = content };
                    }
                    case "GH_BooleanToggle":
                    {
                        var val = obj.GetType().GetProperty("Value")?.GetValue(obj);
                        return new { type = "toggle", val };
                    }
                    case "GH_ValueList":
                    {
                        var selected = obj.GetType().GetProperty("FirstSelectedItem")?.GetValue(obj);
                        if (selected == null) return new { type = "valuelist" };
                        var selName = selected.GetType().GetProperty("Name")?.GetValue(selected)?.ToString();
                        var selVal = selected.GetType().GetProperty("Value")?.GetValue(selected)?.ToString();
                        return new { type = "valuelist", name = selName, val = selVal };
                    }
                    case "GH_ColourSwatch":
                    {
                        var colour = obj.GetType().GetProperty("SwatchColour")?.GetValue(obj);
                        if (colour is Color c)
                            return new { type = "colour", val = $"#{c.R:X2}{c.G:X2}{c.B:X2}" };
                        return new { type = "colour" };
                    }
                    default:
                        return null;
                }
            }
            catch { return null; }
        }

        private object? BuildComponentEntry(object obj, string shortId, string typeName,
            float[]? pos, List<string> errors, List<string> warnings,
            bool includeData, int maxPreviewItems, List<object>? behavioralPointOutputs = null)
        {
            var name = obj.GetType().GetProperty("Name")?.GetValue(obj)?.ToString();
            var nick = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString();
            var category = obj.GetType().GetProperty("Category")?.GetValue(obj)?.ToString();
            var subCategory = obj.GetType().GetProperty("SubCategory")?.GetValue(obj)?.ToString();
            var description = obj.GetType().GetProperty("Description")?.GetValue(obj)?.ToString();

            // Extract component TYPE GUID (stable across installs, identifies the component kind)
            var componentGuid = obj.GetType().GetProperty("ComponentGuid")?.GetValue(obj)?.ToString();

            // Clean type name
            var cleanType = typeName.StartsWith("GH_") ? typeName.Substring(3) : typeName;

            var entry = new Dictionary<string, object?>
            {
                ["id"] = shortId,
                ["type"] = cleanType,
                ["name"] = name
            };

            // Only include nick if different from name
            if (nick != null && nick != name)
                entry["nick"] = nick;

            if (componentGuid != null)
                entry["componentGuid"] = componentGuid;

            if (category != null)
                entry["category"] = category;

            if (!string.IsNullOrEmpty(subCategory))
                entry["subCategory"] = subCategory;

            if (!string.IsNullOrWhiteSpace(description))
                entry["description"] = description;

            if (pos != null)
                entry["pos"] = pos;

            // Extract input/output params
            var paramsProp = obj.GetType().GetProperty("Params");
            if (paramsProp != null)
            {
                var paramsServer = paramsProp.GetValue(obj);
                if (paramsServer != null)
                {
                    var inputs = ExtractParams(paramsServer, true, includeData, maxPreviewItems, null, null);
                    var outputs = ExtractParams(
                        paramsServer,
                        false,
                        includeData,
                        maxPreviewItems,
                        shortId,
                        behavioralPointOutputs);

                    if (inputs != null && ((List<object>)inputs).Count > 0)
                        entry["inputs"] = inputs;
                    if (outputs != null && ((List<object>)outputs).Count > 0)
                        entry["outputs"] = outputs;
                }
            }

            if (errors.Count > 0) entry["errors"] = errors;
            if (warnings.Count > 0) entry["warnings"] = warnings;

            return entry;
        }

        private List<object>? ExtractParams(object paramsServer, bool isInput,
            bool includeData, int maxPreviewItems,
            string? componentShortId = null,
            List<object>? behavioralPointOutputs = null)
        {
            try
            {
                var propName = isInput ? "Input" : "Output";
                var paramList = paramsServer.GetType().GetProperty(propName)?
                    .GetValue(paramsServer) as System.Collections.IEnumerable;
                if (paramList == null) return null;

                var result = new List<object>();
                int idx = 0;
                foreach (var param in paramList)
                {
                    var pName = param.GetType().GetProperty("Name")?.GetValue(param)?.ToString();
                    var pNick = param.GetType().GetProperty("NickName")?.GetValue(param)?.ToString();
                    var pType = param.GetType().GetProperty("TypeName")?.GetValue(param)?.ToString();

                    var entry = new Dictionary<string, object?>
                    {
                        ["idx"] = idx,
                        ["name"] = pName
                    };

                    if (pNick != null && pNick != pName)
                        entry["nick"] = pNick;
                    if (pType != null)
                        entry["type"] = pType;

                    var access = GetParamAccessString(param);
                    if (access != null)
                        entry["access"] = access;

                    var optional = GetParamOptionalFlag(param);
                    if (optional.HasValue)
                        entry["optional"] = optional.Value;

                    var description = param.GetType().GetProperty("Description")?.GetValue(param)?.ToString();
                    if (!string.IsNullOrWhiteSpace(description))
                        entry["description"] = description;

                    if (param.GetType().GetProperty("Hidden")?.GetValue(param) is bool hidden)
                        entry["hidden"] = hidden;

                    if (isInput)
                    {
                        var sources = param.GetType().GetProperty("Sources")?.GetValue(param)
                            as System.Collections.IEnumerable;
                        var sourceCount = sources?.Cast<object>().Count() ?? 0;
                        entry["sources"] = sourceCount;
                    }
                    else
                    {
                        var recipients = param.GetType().GetProperty("Recipients")?.GetValue(param)
                            as System.Collections.IEnumerable;
                        var recipientCount = recipients?.Cast<object>().Count() ?? 0;
                        entry["recipients"] = recipientCount;

                        // Include data preview for outputs
                        if (includeData)
                        {
                            if (behavioralPointOutputs is not null && componentShortId is not null)
                            {
                                var projection = ExtractFencedOutputData(
                                    param,
                                    maxPreviewItems,
                                    componentShortId,
                                    idx);
                                if (projection.LegacyPreview != null)
                                    entry["data"] = projection.LegacyPreview;
                                if (projection.BehavioralPointOutput != null)
                                    behavioralPointOutputs.Add(projection.BehavioralPointOutput);
                            }
                            else
                            {
                                var dataPreview = ExtractDataPreview(param, maxPreviewItems);
                                if (dataPreview != null)
                                    entry["data"] = dataPreview;
                            }
                        }
                    }

                    result.Add(entry);
                    idx++;
                }
                return result;
            }
            catch { return null; }
        }

        private object? ExtractDataPreview(object param, int maxItems)
        {
            try
            {
                var volatileData = param.GetType().GetProperty("VolatileData")?.GetValue(param);
                if (volatileData == null) return null;

                var isEmpty = volatileData.GetType().GetProperty("IsEmpty")?.GetValue(volatileData) as bool? ?? true;
                if (isEmpty) return null;

                var pathCount = volatileData.GetType().GetProperty("PathCount")?.GetValue(volatileData) as int? ?? 0;
                var dataCount = volatileData.GetType().GetProperty("DataCount")?.GetValue(volatileData) as int? ?? 0;

                string structure;
                if (pathCount == 1 && dataCount == 1) structure = "single";
                else if (pathCount == 1) structure = "list";
                else structure = "tree";

                var result = new Dictionary<string, object?>
                {
                    ["structure"] = structure,
                    ["count"] = dataCount
                };

                if (structure == "tree")
                    result["paths"] = pathCount;

                // Get value previews
                var allDataMethod = volatileData.GetType().GetMethod("AllData", new[] { typeof(bool) });
                if (allDataMethod != null)
                {
                    var allData = allDataMethod.Invoke(volatileData, new object[] { false })
                        as System.Collections.IEnumerable;
                    if (allData != null)
                    {
                        var preview = new List<string>();
                        int count = 0;
                        foreach (var item in allData)
                        {
                            if (count >= maxItems) break;
                            var valueProp = item?.GetType().GetProperty("Value");
                            var value = valueProp?.GetValue(item);
                            preview.Add(value?.ToString() ?? item?.ToString() ?? "null");
                            count++;
                        }
                        if (preview.Count > 0)
                            result["preview"] = preview;
                    }
                }

                return result;
            }
            catch { return null; }
        }

        private sealed class FencedOutputProjection
        {
            public object? LegacyPreview { get; init; }
            public object? BehavioralPointOutput { get; init; }
        }

        private FencedOutputProjection ExtractFencedOutputData(
            object param,
            int maxItems,
            string componentShortId,
            int outputIndex)
        {
            try
            {
                var volatileData = param.GetType().GetProperty("VolatileData")?.GetValue(param);
                if (volatileData == null)
                    return new FencedOutputProjection();

                if (volatileData.GetType().GetProperty("DataCount")?.GetValue(volatileData) is not int dataCount ||
                    dataCount < 0)
                {
                    return new FencedOutputProjection();
                }

                var isEmpty = volatileData.GetType().GetProperty("IsEmpty")?.GetValue(volatileData) as bool? ?? true;
                if (isEmpty)
                    return new FencedOutputProjection();

                var pathCount = volatileData.GetType().GetProperty("PathCount")?.GetValue(volatileData) as int? ?? 0;
                var structure = pathCount == 1 && dataCount == 1
                    ? "single"
                    : pathCount == 1
                        ? "list"
                        : "tree";
                var legacy = new Dictionary<string, object?>
                {
                    ["structure"] = structure,
                    ["count"] = dataCount,
                };
                if (structure == "tree")
                    legacy["paths"] = pathCount;

                var allDataMethod = volatileData.GetType().GetMethod("AllData", new[] { typeof(bool) });
                var allData = allDataMethod?.Invoke(volatileData, new object[] { false })
                    as System.Collections.IEnumerable;
                if (allData == null)
                    return new FencedOutputProjection { LegacyPreview = legacy };

                var preview = new List<string>();
                var points = new List<double[]>();
                var observedCount = 0;
                var sawPoint = false;
                var sawNonPoint = false;
                var sawNonfinitePoint = false;
                var dataUnavailable = false;
                var enumerator = allData.GetEnumerator();
                try
                {
                    while (observedCount < maxItems && enumerator.MoveNext())
                    {
                        var item = enumerator.Current;
                        var value = item?.GetType().GetProperty("Value")?.GetValue(item);
                        preview.Add(value?.ToString() ?? item?.ToString() ?? "null");
                        observedCount++;

                        if (value is Rhino.Geometry.Point3d point)
                        {
                            sawPoint = true;
                            if (IsFinite(point.X) && IsFinite(point.Y) && IsFinite(point.Z))
                            {
                                points.Add(new[] { point.X, point.Y, point.Z });
                            }
                            else
                            {
                                sawNonfinitePoint = true;
                            }
                        }
                        else
                        {
                            sawNonPoint = true;
                        }
                    }
                    if (dataCount <= maxItems &&
                        observedCount == maxItems &&
                        enumerator.MoveNext())
                    {
                        observedCount++;
                    }
                }
                catch
                {
                    dataUnavailable = true;
                }
                finally
                {
                    try { (enumerator as IDisposable)?.Dispose(); }
                    catch { dataUnavailable = true; }
                }

                if (preview.Count > 0)
                    legacy["preview"] = preview;

                if (!sawPoint ||
                    param.GetType().GetProperty("Name")?.GetValue(param) is not string outputName)
                {
                    return new FencedOutputProjection { LegacyPreview = legacy };
                }

                string? error = dataUnavailable
                    ? "data_unavailable"
                    : dataCount > maxItems
                        ? "truncated"
                        : observedCount != dataCount
                            ? "count_mismatch"
                            : sawNonPoint
                                ? "non_point_item"
                                : sawNonfinitePoint
                                    ? "nonfinite_coordinate"
                                    : null;

                return new FencedOutputProjection
                {
                    LegacyPreview = legacy,
                    BehavioralPointOutput = new Dictionary<string, object?>
                    {
                        ["component_id"] = componentShortId,
                        ["output_index"] = outputIndex,
                        ["output_name"] = outputName,
                        ["count"] = dataCount,
                        ["complete"] = error is null,
                        ["points"] = points,
                        ["error"] = error,
                    },
                };
            }
            catch
            {
                return new FencedOutputProjection();
            }
        }

        private static bool IsFinite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);

        /// <summary>
        /// Extract flow strings from a regular component's input params.
        /// Scans each input's Sources to build "CX.OY>CZ.IW" flow strings.
        /// </summary>
        private void ExtractComponentFlows(object obj, string tgtShortId,
            Dictionary<Guid, object> guidToObj, HashSet<Guid> relayGuids, List<string> flows)
        {
            try
            {
                var paramsServer = obj.GetType().GetProperty("Params")?.GetValue(obj);
                if (paramsServer == null) return;

                var inputs = paramsServer.GetType().GetProperty("Input")?
                    .GetValue(paramsServer) as System.Collections.IEnumerable;
                if (inputs == null) return;

                int inputIdx = 0;
                foreach (var input in inputs)
                {
                    var sources = input.GetType().GetProperty("Sources")?
                        .GetValue(input) as System.Collections.IEnumerable;
                    if (sources != null)
                    {
                        foreach (var source in sources)
                        {
                            var flow = BuildFlowString(source, tgtShortId, inputIdx, guidToObj, relayGuids);
                            if (flow != null) flows.Add(flow);
                        }
                    }
                    inputIdx++;
                }
            }
            catch { }
        }

        /// <summary>
        /// Extract flow strings for a simple param (slider/panel) that receives input via Sources.
        /// </summary>
        private void ExtractSimpleParamFlows(object obj, string tgtShortId, Guid tgtGuid,
            Dictionary<Guid, object> guidToObj, HashSet<Guid> relayGuids, List<string> flows)
        {
            try
            {
                var sources = obj.GetType().GetProperty("Sources")?
                    .GetValue(obj) as System.Collections.IEnumerable;
                if (sources == null) return;

                foreach (var source in sources)
                {
                    var flow = BuildFlowString(source, tgtShortId, 0, guidToObj, relayGuids);
                    if (flow != null) flows.Add(flow);
                }
            }
            catch { }
        }

        /// <summary>
        /// Build a single flow string from a source param to a target component's input.
        /// Handles relay erasure: if the source owner is a relay, follows through to find the real source.
        /// </summary>
        private string? BuildFlowString(object sourceParam, string tgtShortId, int tgtInputIdx,
            Dictionary<Guid, object> guidToObj, HashSet<Guid> relayGuids)
        {
            try
            {
                // Get the source param's owner component
                var (ownerGuid, outputIdx) = GetParamOwnerAndIndex(sourceParam);
                if (ownerGuid == null) return null;

                // Relay erasure: if owner is a relay, follow through to the real source
                var visited = new HashSet<Guid>();
                while (relayGuids.Contains(ownerGuid.Value) && !visited.Contains(ownerGuid.Value))
                {
                    visited.Add(ownerGuid.Value);
                    if (!guidToObj.TryGetValue(ownerGuid.Value, out var relay)) break;

                    // Get the relay's sources (what feeds into it)
                    var relaySources = relay.GetType().GetProperty("Sources")?
                        .GetValue(relay) as System.Collections.IEnumerable;
                    if (relaySources == null) break;

                    var firstSource = relaySources.Cast<object>().FirstOrDefault();
                    if (firstSource == null) break;

                    var (nextOwner, nextIdx) = GetParamOwnerAndIndex(firstSource);
                    if (nextOwner == null) break;

                    ownerGuid = nextOwner;
                    outputIdx = nextIdx;
                }

                // If we ended up at a relay with no further source, skip
                if (relayGuids.Contains(ownerGuid.Value)) return null;

                var srcShortId = _idRegistry.ResolveReverse(ownerGuid.Value);
                if (srcShortId == null) return null;

                return $"{srcShortId}.O{outputIdx}>{tgtShortId}.I{tgtInputIdx}";
            }
            catch { return null; }
        }

        /// <summary>
        /// Get the owner component's GUID and the output index of a param within that owner.
        /// For simple params (sliders), the param IS the owner and output index is 0.
        /// </summary>
        private (Guid? ownerGuid, int outputIdx) GetParamOwnerAndIndex(object param)
        {
            try
            {
                // Try to find owner via Attributes.Parent.DocObject
                var attr = param.GetType().GetProperty("Attributes")?.GetValue(param);
                var parentAttr = attr?.GetType().GetProperty("Parent")?.GetValue(attr);
                var owner = parentAttr?.GetType().GetProperty("DocObject")?.GetValue(parentAttr);

                // If no parent, the param itself is the doc object (simple param like slider)
                if (owner == null)
                {
                    owner = attr?.GetType().GetProperty("DocObject")?.GetValue(attr);
                }
                if (owner == null) owner = param;

                var ownerGuid = owner.GetType().GetProperty("InstanceGuid")?.GetValue(owner) as Guid?;
                if (ownerGuid == null) return (null, 0);

                // Determine output index: find param in owner's output list
                int outputIdx = 0;

                // Check if owner has Params (regular component)
                var paramsProp = owner.GetType().GetProperty("Params");
                if (paramsProp != null)
                {
                    var paramsServer = paramsProp.GetValue(owner);
                    var outputs = paramsServer?.GetType().GetProperty("Output")?
                        .GetValue(paramsServer) as System.Collections.IEnumerable;
                    if (outputs != null)
                    {
                        int idx = 0;
                        var paramGuid = param.GetType().GetProperty("InstanceGuid")?.GetValue(param) as Guid?;
                        foreach (var output in outputs)
                        {
                            var outGuid = output.GetType().GetProperty("InstanceGuid")?.GetValue(output) as Guid?;
                            if (outGuid == paramGuid)
                            {
                                outputIdx = idx;
                                break;
                            }
                            idx++;
                        }
                    }
                }
                // else: simple param — output index stays 0

                return (ownerGuid, outputIdx);
            }
            catch { return (null, 0); }
        }

        /// <summary>
        /// POST /gh/edit - Apply batch mutations atomically to the canvas.
        /// Accepts create/delete/set_values/connect/disconnect/groups in one call.
        /// Returns updated snapshot.
        /// </summary>
        public ApiResponse ApplyEdit(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body" };

            Dictionary<string, JsonElement>? args;
            try
            {
                args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args == null)
                    return new ApiResponse { Success = false, Data = "Invalid JSON body" };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Invalid JSON: {ex.Message}" };
            }

            var admissionFailure = ValidateEditAdmission(args);
            if (admissionFailure != null)
                return admissionFailure;

            var notReady = EnsureGrasshopperReadyForEdit("gh_edit");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_edit", null, gh.Error);

            // Validate epoch
            if (!args.TryGetValue("epoch", out var epochEl))
                return new ApiResponse { Success = false, Data = "Missing required parameter: epoch" };

            int requestedEpoch = epochEl.GetInt32();
            if (requestedEpoch != _idRegistry.Epoch)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = new
                    {
                        error = "epoch_mismatch",
                        current_epoch = _idRegistry.Epoch,
                        requested_epoch = requestedEpoch,
                        message = "Canvas has changed since last snapshot. Call gh_snapshot first."
                    }
                };
            }

            var errors = new List<string>();
            var tempIdMap = new Dictionary<string, Guid>();
            int created = 0, deleted = 0, valuesSet = 0, connected = 0, disconnected = 0;
            var dirtyObjects = new List<object>();
            string? readinessReceiptId = null;
            GhSolveReadinessReceipt? readinessReceipt = null;
            GhScheduleResult? scheduleResult = null;
            bool postMutationSolveAttempted = false;
            bool mutationCommitUnknown = false;

            bool HasNonEmptyArray(string key) =>
                args.TryGetValue(key, out var value) &&
                value.ValueKind == JsonValueKind.Array &&
                value.GetArrayLength() > 0;

            var solveRelevantMutationRequested =
                HasNonEmptyArray("create") ||
                HasNonEmptyArray("delete") ||
                HasNonEmptyArray("set_values") ||
                HasNonEmptyArray("connect") ||
                HasNonEmptyArray("disconnect");
            if (solveRelevantMutationRequested)
            {
                var issue = BeginMutationReceipt(gh.Document!, gh.Canvas!);
                if (!issue.Issued)
                    return ReadinessIssueFailure(issue.Error!);
                readinessReceiptId = issue.Receipt!.ReceiptId;
            }

            void AddDirty(object? candidate)
            {
                if (candidate != null && !dirtyObjects.Any(existing => ReferenceEquals(existing, candidate)))
                {
                    dirtyObjects.Add(candidate);
                }
            }

            // Each phase records undo BEFORE making changes:
            //   Phase 1 (Create):     RecordAddObjectEvent (after add)
            //   Phase 2 (Disconnect): RecordWireEvent
            //   Phase 3 (Delete):     RecordRemoveObjectEvent
            //   Phase 4 (Set values): RecordGenericObjectEvent
            //   Phase 5 (Connect):    RecordWireEvent
            //   Phase 6 (Groups):     RecordAddObjectEvent / RecordRemoveObjectEvent / RecordGenericObjectEvent
            //
            // GH SDK: "Do not hang on to [UndoUtil], ask for a new one every time you need it."
            // Each phase gets a fresh UndoUtil instance via this helper.
            //
            // DESIGN DECISION: Sub-operation undo granularity.
            // Phases 1 (create), 2 (disconnect), 3 (delete), and 5 (connect) batch
            // their items into one undo record per phase. However, phase 4 (set_values)
            // records per item (fresh UndoUtil inside the loop), and phase 6 (groups)
            // records per group operation (fresh UndoUtil per EditGroup call).
            // A single /gh/edit may therefore require multiple Ctrl+Z presses.
            // This gives users fine-grained control. To merge into a single undo
            // record, use Create*Event (returns GH_UndoRecord) instead of Record*Event
            // and manually merge records — not implemented.
            object? GetFreshUndoUtil()
            {
                try { return gh.Document!.GetType().GetProperty("UndoUtil")?.GetValue(gh.Document); }
                catch { return null; }
            }

            GhMutationSolveSuspension? solveSuspension = null;
            GhSolverRestoreResult? standaloneRestore = null;

            try
            {
                solveSuspension = BeginPostMutationBatchSolveSuspension(gh.Document!);

                // Phase 1: Create components
                var createdObjects = new List<object>();
                if (args.TryGetValue("create", out var createEl) && createEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in createEl.EnumerateArray())
                    {
                        try
                        {
                            var result = EditCreateComponent(gh, item);
                            if (result.guid != null)
                            {
                                var tempId = item.TryGetProperty("temp_id", out var tid)
                                    ? tid.GetString() : null;
                                if (tempId != null)
                                    tempIdMap[tempId] = result.guid.Value;
                                _idRegistry.Register(result.guid.Value);
                                created++;

                                // Track created object for undo recording
                                if (result.component != null)
                                {
                                    createdObjects.Add(result.component);
                                    AddDirty(result.component);
                                }
                            }
                            else
                            {
                                errors.Add($"Create failed: {result.error}");
                            }
                        }
                        catch (Exception ex)
                        {
                            mutationCommitUnknown = true;
                            errors.Add($"Create exception: {ex.Message}");
                        }
                    }

                    // Record undo event for all created objects as a single batch
                    if (createdObjects.Count > 0)
                    {
                        try
                        {
                            var uu = GetFreshUndoUtil();
                            if (uu != null)
                                RecordUndoEvent(uu, "Rook: create components", createdObjects, isAdd: true);
                        }
                        catch { /* undo recording is best-effort */ }
                    }
                }

                // Phase 2: Disconnect (before delete so users can unwire then remove in one batch)
                // Phase 3: Delete
                // Phase 4: Set values

                // --- Phase 2: Disconnect ---
                if (args.TryGetValue("disconnect", out var discEl) && discEl.ValueKind == JsonValueKind.Array)
                {
                    // Collect target params for batch undo recording, then disconnect
                    var disconnectOps = new List<(object sourceOutput, object targetInput, string flowStr)>();
                    var disconnectParams = new List<object>();

                    foreach (var item in discEl.EnumerateArray())
                    {
                        var flowStr = item.GetString();
                        if (flowStr == null) continue;

                        try
                        {
                            var (srcId, srcIdx, tgtId, tgtIdx) = ParseFlowString(flowStr);
                            var srcGuid = ResolveEditId(srcId, tempIdMap);
                            var tgtGuid = ResolveEditId(tgtId, tempIdMap);
                            if (srcGuid == null) { errors.Add($"disconnect: unknown source '{srcId}'"); continue; }
                            if (tgtGuid == null) { errors.Add($"disconnect: unknown target '{tgtId}'"); continue; }

                            var srcObj = FindObjectById(gh.Document!, srcGuid.Value.ToString());
                            var tgtObj = FindObjectById(gh.Document!, tgtGuid.Value.ToString());
                            if (srcObj == null || tgtObj == null) { errors.Add($"disconnect: object not found for '{flowStr}'"); continue; }

                            var sourceOutput = GetParam(srcObj, false, srcIdx, null);
                            var targetInput = GetParam(tgtObj, true, tgtIdx, null);
                            if (sourceOutput == null || targetInput == null) { errors.Add($"disconnect: param not found for '{flowStr}'"); continue; }

                            disconnectOps.Add((sourceOutput, targetInput, flowStr));
                            disconnectParams.Add(targetInput);
                        }
                        catch (Exception ex)
                        {
                            errors.Add($"disconnect '{flowStr}': {ex.Message}");
                        }
                    }

                    // Record wire undo BEFORE disconnecting
                    if (disconnectParams.Count > 0)
                    {
                        try
                        {
                            var uu = GetFreshUndoUtil();
                            if (uu != null)
                                RecordWireUndoEvent(uu, "Rook: disconnect wires", disconnectParams);
                        }
                        catch { /* undo recording is best-effort */ }
                    }

                    // Now perform the disconnects
                    foreach (var (sourceOutput, targetInput, flowStr) in disconnectOps)
                    {
                        try
                        {
                            var paramType = gh.Assembly!.GetType("Grasshopper.Kernel.IGH_Param");
                            var removeMethod = paramType is null
                                ? null
                                : targetInput.GetType().GetMethod("RemoveSource", new[] { paramType });
                            if (removeMethod is null)
                            {
                                errors.Add($"disconnect '{flowStr}': RemoveSource mutator unavailable");
                                continue;
                            }

                            try
                            {
                                removeMethod.Invoke(targetInput, new[] { sourceOutput });
                            }
                            catch
                            {
                                mutationCommitUnknown = true;
                                throw;
                            }
                            disconnected++;
                            AddDirty(targetInput);
                        }
                        catch (Exception ex)
                        {
                            errors.Add($"disconnect '{flowStr}': {ex.Message}");
                        }
                    }
                }

                // --- Phase 3: Delete ---
                if (args.TryGetValue("delete", out var deleteEl) && deleteEl.ValueKind == JsonValueKind.Array)
                {
                    // Hoist RemoveObject method lookup outside the loop
                    var removeMethod = gh.Document!.GetType().GetMethods()
                        .FirstOrDefault(m => m.Name == "RemoveObject" &&
                            m.GetParameters().Length == 2 &&
                            m.GetParameters()[1].ParameterType == typeof(bool));

                    // First pass: collect objects to delete (for undo recording BEFORE removal)
                    var deletedObjects = new List<object>();
                    var deletedAttrs = new List<(object attributes, string shortId)>();

                    foreach (var item in deleteEl.EnumerateArray())
                    {
                        var shortId = item.GetString();
                        if (shortId == null) continue;

                        var guid = _idRegistry.Resolve(shortId);
                        if (guid == null)
                        {
                            errors.Add($"Delete: unknown ID '{shortId}'");
                            continue;
                        }

                        var obj = FindObjectById(gh.Document!, guid.Value.ToString());
                        if (obj == null)
                        {
                            errors.Add($"Delete: object '{shortId}' not found on canvas");
                            continue;
                        }

                        var attrProp = obj.GetType().GetProperty("Attributes");
                        var attributes = attrProp?.GetValue(obj);
                        if (attributes != null)
                        {
                            deletedObjects.Add(obj);
                            deletedAttrs.Add((attributes, shortId));
                        }
                        else
                        {
                            errors.Add($"Delete: object '{shortId}' has no attributes");
                        }
                    }

                    // Record undo BEFORE deletion so it captures wire state
                    if (deletedObjects.Count > 0)
                    {
                        try
                        {
                            var uu = GetFreshUndoUtil();
                            if (uu != null)
                                RecordUndoEvent(uu, "Rook: delete components", deletedObjects, isAdd: false);
                        }
                        catch { /* undo recording is best-effort */ }
                    }

                    // Second pass: actually remove the objects
                    foreach (var (attributes, shortId) in deletedAttrs)
                    {
                        if (removeMethod is null)
                        {
                            errors.Add($"Delete: RemoveObject mutator unavailable for '{shortId}'");
                            continue;
                        }

                        try
                        {
                            var removeResult = removeMethod.Invoke(gh.Document, new object[] { attributes, true });
                            if (removeResult is not bool removed)
                            {
                                mutationCommitUnknown = true;
                                errors.Add($"Delete '{shortId}': RemoveObject returned a non-Boolean result");
                                continue;
                            }
                            if (!removed)
                            {
                                errors.Add($"Delete '{shortId}': RemoveObject returned false");
                                continue;
                            }
                            deleted++;
                        }
                        catch (Exception ex)
                        {
                            mutationCommitUnknown = true;
                            errors.Add($"Delete '{shortId}' exception: {ex.Message}");
                        }
                    }
                }

                // --- Phase 4: Set values ---
                if (args.TryGetValue("set_values", out var setValEl) && setValEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in setValEl.EnumerateArray())
                    {
                        var itemCommitted = false;
                        try
                        {
                            var id = item.TryGetProperty("id", out var idEl) ? idEl.GetString() : null;
                            if (id == null) { errors.Add("set_values: missing 'id'"); continue; }

                            var guid = ResolveEditId(id, tempIdMap);
                            if (guid == null) { errors.Add($"set_values: unknown ID '{id}'"); continue; }

                            var obj = FindObjectById(gh.Document!, guid.Value.ToString());
                            if (obj == null) { errors.Add($"set_values: object '{id}' not found"); continue; }

                            // Record generic object undo BEFORE changing values
                            try
                            {
                                var uu = GetFreshUndoUtil();
                                if (uu != null)
                                    RecordGenericObjectUndoEvent(uu, "Rook: set values", obj);
                            }
                            catch { /* undo recording is best-effort */ }

                            var typeName = obj.GetType().Name;
                            var requestedMutableField = false;

                            void MarkItemCommitted()
                            {
                                if (!itemCommitted)
                                {
                                    valuesSet++;
                                    itemCommitted = true;
                                    AddDirty(obj);
                                }
                            }

                            void SetRequiredProperty(object target, string propertyName, object? value)
                            {
                                var property = target.GetType().GetProperty(propertyName);
                                if (property is null)
                                {
                                    errors.Add($"set_values '{id}': {propertyName} mutator unavailable");
                                    return;
                                }

                                try
                                {
                                    property.SetValue(target, value);
                                }
                                catch
                                {
                                    if (!itemCommitted)
                                        mutationCommitUnknown = true;
                                    throw;
                                }

                                MarkItemCommitted();
                            }

                            // NickName — works on any component type (base class property)
                            if (item.TryGetProperty("nick", out var nickEl2))
                            {
                                requestedMutableField = true;
                                var nickVal = nickEl2.GetString();
                                if (nickVal != null)
                                {
                                    SetRequiredProperty(obj, "NickName", nickVal);
                                }
                            }

                            if (typeName == "GH_NumberSlider")
                            {
                                var slider = obj.GetType().GetProperty("Slider")?.GetValue(obj);
                                if (slider != null)
                                {
                                    var sliderType = slider.GetType();
                                    // Batch edits defer solving until the end of the edit.
                                    // Doing per-control ExpireSolution calls here can re-enter
                                    // the GH UI callback and has caused bridge timeouts in practice.
                                    // Set max before min to avoid transient min>max state
                                    // when expanding range upward (e.g. [0,10] → [20,30])
                                    if (item.TryGetProperty("max", out var maxEl))
                                    {
                                        requestedMutableField = true;
                                        SetRequiredProperty(slider, "Maximum", maxEl.GetDecimal());
                                    }
                                    if (item.TryGetProperty("min", out var minEl))
                                    {
                                        requestedMutableField = true;
                                        SetRequiredProperty(slider, "Minimum", minEl.GetDecimal());
                                    }
                                    if (item.TryGetProperty("value", out var valEl2))
                                    {
                                        requestedMutableField = true;
                                        SetRequiredProperty(slider, "Value", valEl2.GetDecimal());
                                    }
                                }
                                else
                                {
                                    errors.Add($"set_values '{id}': Slider object unavailable");
                                }
                            }
                            else if (typeName == "GH_Panel")
                            {
                                if (item.TryGetProperty("value", out var valEl2))
                                {
                                    requestedMutableField = true;
                                    SetRequiredProperty(obj, "UserText", valEl2.GetString());
                                }
                            }
                            else if (typeName == "GH_BooleanToggle")
                            {
                                if (item.TryGetProperty("value", out var valEl2))
                                {
                                    requestedMutableField = true;
                                    SetRequiredProperty(obj, "Value", valEl2.GetBoolean());
                                }
                            }

                            if (!requestedMutableField)
                                errors.Add($"set_values '{id}': no mutable fields supplied");
                        }
                        catch (Exception ex)
                        {
                            errors.Add($"set_values exception: {ex.Message}");
                        }
                    }
                }

                // --- Phase 5: Connect ---
                if (args.TryGetValue("connect", out var connEl) && connEl.ValueKind == JsonValueKind.Array)
                {
                    // Collect target params for batch undo recording, then connect
                    var connectOps = new List<(object sourceOutput, object targetInput, string flowStr)>();
                    var connectParams = new List<object>();

                    foreach (var item in connEl.EnumerateArray())
                    {
                        var flowStr = item.GetString();
                        if (flowStr == null) continue;

                        try
                        {
                            var (srcId, srcIdx, tgtId, tgtIdx) = ParseFlowString(flowStr);
                            var srcGuid = ResolveEditId(srcId, tempIdMap);
                            var tgtGuid = ResolveEditId(tgtId, tempIdMap);
                            if (srcGuid == null) { errors.Add($"connect: unknown source '{srcId}'"); continue; }
                            if (tgtGuid == null) { errors.Add($"connect: unknown target '{tgtId}'"); continue; }

                            var srcObj = FindObjectById(gh.Document!, srcGuid.Value.ToString());
                            var tgtObj = FindObjectById(gh.Document!, tgtGuid.Value.ToString());
                            if (srcObj == null || tgtObj == null) { errors.Add($"connect: object not found for '{flowStr}'"); continue; }

                            var sourceOutput = GetParam(srcObj, false, srcIdx, null);
                            var targetInput = GetParam(tgtObj, true, tgtIdx, null);
                            if (sourceOutput == null || targetInput == null) { errors.Add($"connect: param not found for '{flowStr}'"); continue; }

                            connectOps.Add((sourceOutput, targetInput, flowStr));
                            connectParams.Add(targetInput);
                        }
                        catch (Exception ex)
                        {
                            errors.Add($"connect '{flowStr}': {ex.Message}");
                        }
                    }

                    // Record wire undo BEFORE connecting
                    if (connectParams.Count > 0)
                    {
                        try
                        {
                            var uu = GetFreshUndoUtil();
                            if (uu != null)
                                RecordWireUndoEvent(uu, "Rook: connect wires", connectParams);
                        }
                        catch { /* undo recording is best-effort */ }
                    }

                    // Now perform the connections
                    foreach (var (sourceOutput, targetInput, flowStr) in connectOps)
                    {
                        try
                        {
                            var paramType = gh.Assembly!.GetType("Grasshopper.Kernel.IGH_Param");
                            var addMethod = paramType is null
                                ? null
                                : targetInput.GetType().GetMethod("AddSource", new[] { paramType });
                            if (addMethod is null)
                            {
                                errors.Add($"connect '{flowStr}': AddSource mutator unavailable");
                                continue;
                            }

                            try
                            {
                                addMethod.Invoke(targetInput, new[] { sourceOutput });
                            }
                            catch
                            {
                                mutationCommitUnknown = true;
                                throw;
                            }
                            connected++;
                            AddDirty(targetInput);
                        }
                        catch (Exception ex)
                        {
                            errors.Add($"connect '{flowStr}': {ex.Message}");
                        }
                    }
                }

                // --- Phase 6: Groups ---
                if (args.TryGetValue("groups", out var grpEl) && grpEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in grpEl.EnumerateArray())
                    {
                        try
                        {
                            EditGroup(gh, item, tempIdMap, GetFreshUndoUtil());
                        }
                        catch (Exception ex)
                        {
                            errors.Add($"group: {ex.Message}");
                        }
                    }
                }

                // Phase 7: Mark changed objects dirty, but do not schedule yet. The
                // response snapshot must be captured before any scheduled Chirp solve
                // can monopolize the UI thread and trip the native callback timeout.
                var solveRelevantCommitCount = created + deleted + valuesSet + connected + disconnected;
                var changedObjects = solveRelevantCommitCount > 0;
                ExpirePostMutationDirtyObjects(dirtyObjects);
                RefreshCanvas(gh.Canvas!, scheduleSolution: false);

                // Phase 8: Capture committed topology before scheduling the solve.
                // Do not read output previews here: after dirty expiration, data
                // preview extraction can force expensive Chirp solve paths inside
                // the native callback.
                var snapshotResult = TakeStructuralSnapshot();

                // Phase 9: Restore standalone solver ownership exactly once,
                // then request exactly one positive-delay schedule.
                const int postEditSolveDelayMs = 1;
                standaloneRestore = solveSuspension.Restore();
                postMutationSolveAttempted = changedObjects;
                scheduleResult = RequestPostMutationSolve(
                    gh.Document!,
                    dirtyObjects,
                    requestSolve: changedObjects,
                    delayMs: postEditSolveDelayMs,
                    expireDirtyObjects: false,
                    standaloneRestore: standaloneRestore);
                var solveResult = scheduleResult.Value;
                if (readinessReceiptId is not null)
                {
                    readinessReceipt = changedObjects
                        ? FinalizeMutationReceipt(readinessReceiptId, solveResult)
                        : mutationCommitUnknown
                            ? FinalizeUnknownCommitReceipt(readinessReceiptId)
                            : FinalizeNoCommitReceipt(readinessReceiptId);
                }

                var editSummary = new
                {
                    created, deleted, values_set = valuesSet,
                    connected, disconnected,
                    schedule_classification = GhScheduleWire.ToWire(solveResult.ScheduleClassification),
                    schedule_acceptance = GhScheduleWire.ToWire(solveResult.ScheduleAcceptance),
                    schedule_failure_code = solveResult.ScheduleFailureCode.HasValue
                        ? GhScheduleWire.ToWire(solveResult.ScheduleFailureCode.Value)
                        : null,
                    solve_scheduled = solveResult.SolveScheduled,
                    registration_known = solveResult.RegistrationKnown,
                    document_registered = solveResult.DocumentRegistered,
                    solver_locked = solveResult.SolverLocked,
                    solver_state_known = solveResult.SolverStateKnown,
                    verification_deferred = solveResult.VerificationDeferred,
                    rir_repair_attempted = false,
                    rir_repair_held = false,
                    rir_repair_reason = (string?)null,
                    solve_warnings = solveResult.Warnings.Select(GhScheduleWire.ToWire).ToArray(),
                    standalone_restore_attempted = standaloneRestore.Value.Attempted,
                    standalone_restore_succeeded = standaloneRestore.Value.Succeeded,
                    observed_document_enabled = standaloneRestore.Value.ObservedDocumentEnabled,
                    errors = errors.Count > 0 ? errors : null,
                    temp_id_map = tempIdMap.Count > 0
                        ? tempIdMap.ToDictionary(
                            kv => kv.Key,
                            kv => _idRegistry.ResolveReverse(kv.Value) ?? kv.Value.ToString())
                        : null,
                    instance_guids = tempIdMap.Count > 0
                        ? tempIdMap.ToDictionary(
                            kv => kv.Key,
                            kv => kv.Value.ToString())
                        : null
                };

                if (snapshotResult.Success && snapshotResult.Data is Dictionary<string, object?> snapData)
                {
                    snapData["edit_summary"] = editSummary;
                    if (readinessReceipt is not null)
                        snapData["solve_readiness_receipt"] = ReceiptSnapshot(readinessReceipt);
                }
                else if (snapshotResult.Success)
                {
                    // Snapshot returned non-dictionary data, wrap it
                    var wrappedSuccess = new Dictionary<string, object?>
                    {
                        ["snapshot"] = snapshotResult.Data,
                        ["edit_summary"] = editSummary,
                    };
                    if (readinessReceipt is not null)
                        wrappedSuccess["solve_readiness_receipt"] = ReceiptSnapshot(readinessReceipt);
                    snapshotResult.Data = wrappedSuccess;
                }
                else
                {
                    var snapshotFailure = snapshotResult.Data;
                    var wrappedFailure = new Dictionary<string, object?>
                    {
                        ["snapshot_failure"] = snapshotFailure,
                        ["edit_summary"] = editSummary,
                    };
                    if (readinessReceipt is not null)
                        wrappedFailure["solve_readiness_receipt"] = ReceiptSnapshot(readinessReceipt);
                    snapshotResult.Data = wrappedFailure;
                }

                return snapshotResult;
            }
            catch (Exception ex)
            {
                if (!standaloneRestore.HasValue && solveSuspension != null)
                    standaloneRestore = solveSuspension.Restore();

                var solveRelevantCommitCount = created + deleted + valuesSet + connected + disconnected;
                bool? solveRelevantMutationCommitted = solveRelevantCommitCount > 0
                    ? true
                    : mutationCommitUnknown
                        ? null
                        : false;
                if (readinessReceiptId is not null && readinessReceipt is null)
                {
                    if (solveRelevantMutationCommitted == false)
                    {
                        readinessReceipt = FinalizeNoCommitReceipt(readinessReceiptId);
                    }
                    else if (solveRelevantMutationCommitted is null)
                    {
                        readinessReceipt = FinalizeUnknownCommitReceipt(readinessReceiptId);
                    }
                    else if (scheduleResult.HasValue)
                    {
                        readinessReceipt = FinalizeMutationReceipt(readinessReceiptId, scheduleResult.Value);
                    }
                    else if (postMutationSolveAttempted)
                    {
                        readinessReceipt = FinalizePostReservationFailureReceipt(
                            readinessReceiptId,
                            solveRelevantMutationCommitted: true);
                    }
                    else
                    {
                        readinessReceipt = FinalizePostReservationFailureReceipt(
                            readinessReceiptId,
                            solveRelevantMutationCommitted: true,
                            scheduleCommittedMutation: () =>
                            {
                                postMutationSolveAttempted = true;
                                scheduleResult = RequestPostMutationSolve(
                                    gh.Document!,
                                    dirtyObjects,
                                    requestSolve: true,
                                    delayMs: 1,
                                    expireDirtyObjects: false,
                                    standaloneRestore: standaloneRestore);
                                return scheduleResult.Value;
                            });
                    }
                }

                var registration = new GhDocumentLifecycle().InspectRegistration(gh.Document!);
                var effectiveSchedule = scheduleResult ?? new GhScheduleResult
                {
                    RegistrationKnown = registration.Known,
                    DocumentRegistered = registration.Known ? registration.Registered : (bool?)null,
                    ScheduleClassification = GhScheduleClassification.SolveNotRequested,
                    ScheduleAcceptance = GhScheduleAcceptance.NotAttempted,
                    ScheduleFailureCode = standaloneRestore.HasValue &&
                        standaloneRestore.Value.Attempted &&
                        !standaloneRestore.Value.Succeeded
                            ? GhScheduleFailureCode.StandaloneSolverRestoreFailed
                            : null,
                    VerificationDeferred = solveRelevantMutationCommitted == true,
                    Warnings = standaloneRestore.HasValue &&
                        standaloneRestore.Value.Attempted &&
                        !standaloneRestore.Value.Succeeded
                            ? new[] { GhScheduleWarning.StandaloneRestoreFailed }
                            : Array.Empty<GhScheduleWarning>(),
                };
                var failureSummary = new
                {
                    created,
                    deleted,
                    values_set = valuesSet,
                    connected,
                    disconnected,
                    schedule_classification = GhScheduleWire.ToWire(effectiveSchedule.ScheduleClassification),
                    schedule_acceptance = GhScheduleWire.ToWire(effectiveSchedule.ScheduleAcceptance),
                    schedule_failure_code = effectiveSchedule.ScheduleFailureCode.HasValue
                        ? GhScheduleWire.ToWire(effectiveSchedule.ScheduleFailureCode.Value)
                        : null,
                    solve_scheduled = effectiveSchedule.SolveScheduled,
                    registration_known = effectiveSchedule.RegistrationKnown,
                    document_registered = effectiveSchedule.DocumentRegistered,
                    solver_locked = effectiveSchedule.SolverLocked,
                    solver_state_known = effectiveSchedule.SolverStateKnown,
                    verification_deferred = effectiveSchedule.VerificationDeferred,
                    solve_warnings = effectiveSchedule.Warnings.Select(GhScheduleWire.ToWire).ToArray(),
                    standalone_restore_attempted = standaloneRestore?.Attempted ?? false,
                    standalone_restore_succeeded = standaloneRestore?.Succeeded,
                    observed_document_enabled = standaloneRestore?.ObservedDocumentEnabled,
                    errors = errors.Count > 0 ? errors : null,
                    temp_id_map = tempIdMap.Count > 0
                        ? tempIdMap.ToDictionary(
                            kv => kv.Key,
                            kv => _idRegistry.ResolveReverse(kv.Value) ?? kv.Value.ToString())
                        : null,
                    instance_guids = tempIdMap.Count > 0
                        ? tempIdMap.ToDictionary(kv => kv.Key, kv => kv.Value.ToString())
                        : null,
                };

                var failureData = new Dictionary<string, object?>
                {
                    ["error"] = "apply_edit_failed",
                    ["message"] = ex.Message,
                    ["edit_summary"] = failureSummary,
                };
                if (readinessReceipt is not null)
                    failureData["solve_readiness_receipt"] = ReceiptSnapshot(readinessReceipt);

                return new ApiResponse { Success = false, Data = failureData };
            }
        }

        private ApiResponse? ValidateEditAdmission(Dictionary<string, JsonElement> args)
        {
            var issues = new List<Dictionary<string, object?>>();
            var declared = new HashSet<string>(StringComparer.Ordinal);

            void AddIssue(string path, string code, object? value)
            {
                issues.Add(new Dictionary<string, object?>
                {
                    ["path"] = path,
                    ["code"] = code,
                    ["value"] = value,
                });
            }

            object? Retain(JsonElement value) =>
                value.ValueKind == JsonValueKind.Undefined ? null : value.Clone();

            void ScanReference(string path, object? value)
            {
                if (value is string text && GhEditTempIdRegex.IsMatch(text))
                {
                    if (!declared.Contains(text))
                        AddIssue(path, "unresolved_temp_reference", text);
                    return;
                }
                if (value is string componentId && GhEditComponentIdRegex.IsMatch(componentId))
                    return;
                AddIssue(path, "invalid_component_reference", value);
            }

            if (args.TryGetValue("create", out var createElement))
            {
                if (createElement.ValueKind != JsonValueKind.Array)
                {
                    AddIssue("/create", "invalid_temp_id", Retain(createElement));
                }
                else
                {
                    var index = 0;
                    foreach (var item in createElement.EnumerateArray())
                    {
                        var path = $"/create/{index}/temp_id";
                        JsonElement tempElement = default;
                        var hasTemp = item.ValueKind == JsonValueKind.Object &&
                            item.TryGetProperty("temp_id", out tempElement);
                        var value = hasTemp && tempElement.ValueKind == JsonValueKind.String
                            ? tempElement.GetString()
                            : null;
                        if (value == null || !GhEditTempIdRegex.IsMatch(value))
                        {
                            AddIssue(path, "invalid_temp_id", hasTemp ? Retain(tempElement) : null);
                        }
                        else if (!declared.Add(value))
                        {
                            AddIssue(path, "duplicate_temp_id", value);
                        }
                        index++;
                    }
                }
            }

            void ScanFlows(string field)
            {
                if (!args.TryGetValue(field, out var flows))
                    return;
                if (flows.ValueKind != JsonValueKind.Array)
                {
                    AddIssue($"/{field}", "invalid_flow", Retain(flows));
                    return;
                }

                var index = 0;
                foreach (var item in flows.EnumerateArray())
                {
                    var path = $"/{field}/{index}";
                    var flow = item.ValueKind == JsonValueKind.String ? item.GetString() : null;
                    if (flow == null)
                    {
                        AddIssue(path, "invalid_flow", Retain(item));
                        index++;
                        continue;
                    }
                    try
                    {
                        var (sourceId, _, targetId, _) = ParseFlowString(flow);
                        ScanReference(path, sourceId);
                        ScanReference(path, targetId);
                    }
                    catch
                    {
                        AddIssue(path, "invalid_flow", flow);
                    }
                    index++;
                }
            }

            ScanFlows("disconnect");

            if (args.TryGetValue("set_values", out var setValues))
            {
                if (setValues.ValueKind != JsonValueKind.Array)
                {
                    AddIssue("/set_values", "invalid_component_reference", Retain(setValues));
                }
                else
                {
                    var index = 0;
                    foreach (var item in setValues.EnumerateArray())
                    {
                        JsonElement idElement = default;
                        var hasId = item.ValueKind == JsonValueKind.Object &&
                            item.TryGetProperty("id", out idElement);
                        object? value = hasId && idElement.ValueKind == JsonValueKind.String
                            ? idElement.GetString()
                            : hasId ? Retain(idElement) : null;
                        ScanReference($"/set_values/{index}/id", value);
                        index++;
                    }
                }
            }

            ScanFlows("connect");

            if (args.TryGetValue("groups", out var groups))
            {
                if (groups.ValueKind != JsonValueKind.Array)
                {
                    AddIssue("/groups", "invalid_component_reference", Retain(groups));
                }
                else
                {
                    var groupIndex = 0;
                    foreach (var group in groups.EnumerateArray())
                    {
                        if (group.ValueKind != JsonValueKind.Object ||
                            !group.TryGetProperty("members", out var members))
                        {
                            groupIndex++;
                            continue;
                        }
                        if (members.ValueKind != JsonValueKind.Array)
                        {
                            AddIssue(
                                $"/groups/{groupIndex}/members",
                                "invalid_component_reference",
                                Retain(members));
                            groupIndex++;
                            continue;
                        }

                        var memberIndex = 0;
                        foreach (var member in members.EnumerateArray())
                        {
                            object? value = member.ValueKind == JsonValueKind.String
                                ? member.GetString()
                                : Retain(member);
                            ScanReference(
                                $"/groups/{groupIndex}/members/{memberIndex}",
                                value);
                            memberIndex++;
                        }
                        groupIndex++;
                    }
                }
            }

            if (issues.Count == 0)
                return null;
            return new ApiResponse
            {
                Success = false,
                Data = new Dictionary<string, object?>
                {
                    ["error"] = "gh_edit_admission_failed",
                    ["issues"] = issues,
                },
            };
        }

        /// <summary>
        /// Parse a flow string "C1.O0>C2.I1" into (srcId, srcIdx, tgtId, tgtIdx).
        /// </summary>
        private (string srcId, int srcIdx, string tgtId, int tgtIdx) ParseFlowString(string flow)
        {
            var parts = flow.Split('>');
            if (parts.Length != 2)
                throw new ArgumentException($"Invalid flow string: '{flow}'");

            var src = parts[0].Split('.');
            var tgt = parts[1].Split('.');
            if (src.Length != 2 || tgt.Length != 2)
                throw new ArgumentException($"Invalid flow string format: '{flow}'");

            var srcId = src[0];
            var tgtId = tgt[0];

            // Parse O0/I1 notation
            var srcRef = src[1];
            var tgtRef = tgt[1];

            if (srcRef.Length < 2 || (srcRef[0] != 'O' && srcRef[0] != 'o'))
                throw new ArgumentException($"Invalid source param ref '{srcRef}' in '{flow}' (expected O{{n}})");
            if (tgtRef.Length < 2 || (tgtRef[0] != 'I' && tgtRef[0] != 'i'))
                throw new ArgumentException($"Invalid target param ref '{tgtRef}' in '{flow}' (expected I{{n}})");

            int srcIdx = int.Parse(srcRef.Substring(1));
            int tgtIdx = int.Parse(tgtRef.Substring(1));

            if (srcIdx < 0) throw new ArgumentException($"Negative output index in '{flow}'");
            if (tgtIdx < 0) throw new ArgumentException($"Negative input index in '{flow}'");

            return (srcId, srcIdx, tgtId, tgtIdx);
        }

        /// <summary>
        /// Resolve a short ID (C*) or temp ID (T*) to a GUID.
        /// </summary>
        private Guid? ResolveEditId(string id, Dictionary<string, Guid> tempIdMap)
        {
            if (id.StartsWith("T", StringComparison.OrdinalIgnoreCase) && tempIdMap.TryGetValue(id, out var tempGuid))
                return tempGuid;
            return _idRegistry.Resolve(id);
        }

        /// <summary>
        /// Create a single component from a batch edit entry.
        /// Returns the new InstanceGuid, the component object (for undo recording), or an error message.
        /// </summary>
        private (Guid? guid, object? component, string? error) EditCreateComponent(GrasshopperContext gh, JsonElement item)
        {
            float x = 100, y = 100;
            if (item.TryGetProperty("pos", out var posEl) && posEl.ValueKind == JsonValueKind.Array)
            {
                var posArr = posEl.EnumerateArray().ToList();
                if (posArr.Count >= 2)
                {
                    x = posArr[0].GetSingle();
                    y = posArr[1].GetSingle();
                }
            }

            // Determine creation type
            string? specialType = item.TryGetProperty("type", out var typeEl) ? typeEl.GetString() : null;
            string? guidStr = item.TryGetProperty("guid", out var guidEl) ? guidEl.GetString() : null;
            string? name = item.TryGetProperty("name", out var nameEl) ? nameEl.GetString() : null;

            object? component = null;

            if (specialType == "slider")
            {
                var sliderType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_NumberSlider");
                if (sliderType == null) return (null, null, "GH_NumberSlider type not found");

                component = Activator.CreateInstance(sliderType);
                if (component == null) return (null, null, "Failed to create slider");

                // Set nickname
                var nick = item.TryGetProperty("nick", out var nickEl) ? nickEl.GetString() : "Slider";
                sliderType.GetProperty("NickName")?.SetValue(component, nick);

                // Set range/value
                var sliderProp = sliderType.GetProperty("Slider");
                var sliderObj = sliderProp?.GetValue(component);
                if (sliderObj != null)
                {
                    var st = sliderObj.GetType();
                    // Set max before min to avoid transient min>max state
                    if (item.TryGetProperty("max", out var maxEl)) st.GetProperty("Maximum")?.SetValue(sliderObj, maxEl.GetDecimal());
                    if (item.TryGetProperty("min", out var minEl)) st.GetProperty("Minimum")?.SetValue(sliderObj, minEl.GetDecimal());
                    if (item.TryGetProperty("value", out var valEl)) st.GetProperty("Value")?.SetValue(sliderObj, valEl.GetDecimal());
                }
            }
            else if (specialType == "panel")
            {
                var panelType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Panel");
                if (panelType == null) return (null, null, "GH_Panel type not found");

                component = Activator.CreateInstance(panelType);
                if (component == null) return (null, null, "Failed to create panel");

                var content = item.TryGetProperty("content", out var contentEl)
                    ? contentEl.GetString() ?? "" : "";
                panelType.GetProperty("UserText")?.SetValue(component, content);
            }
            else if (specialType == "toggle")
            {
                var toggleType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_BooleanToggle");
                if (toggleType == null) return (null, null, "GH_BooleanToggle type not found");

                component = Activator.CreateInstance(toggleType);
                if (component == null) return (null, null, "Failed to create toggle");

                if (item.TryGetProperty("value", out var valEl))
                    toggleType.GetProperty("Value")?.SetValue(component, valEl.GetBoolean());
            }
            else if (!string.IsNullOrEmpty(guidStr) && Guid.TryParse(guidStr, out var componentGuid))
            {
                // Create by GUID — proxy-first resolution (handles GhPython + native)
                var instancesType = gh.Assembly!.GetType("Grasshopper.Instances");
                var server = instancesType?.GetProperty("ComponentServer", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
                if (server == null) return (null, null, "ComponentServer not available");

                component = CreateComponentFromGuid(server, componentGuid, name);
                if (component == null) return (null, null, $"Failed to create component for GUID '{guidStr}'");
            }
            else if (!string.IsNullOrEmpty(name))
            {
                // Create by name
                var instancesType = gh.Assembly!.GetType("Grasshopper.Instances");
                var server = instancesType?.GetProperty("ComponentServer", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
                if (server == null) return (null, null, "ComponentServer not available");

                var proxies = server.GetType().GetProperty("ObjectProxies")?.GetValue(server)
                    as System.Collections.IEnumerable;
                if (proxies == null) return (null, null, "ObjectProxies not available");

                var nameLower = name.ToLowerInvariant();
                const int maxMatches = 5;
                var matches = new List<(object proxy, string fullName)>();
                foreach (var proxy in proxies)
                {
                    var desc = proxy.GetType().GetProperty("Desc")?.GetValue(proxy);
                    var pName = desc?.GetType().GetProperty("Name")?.GetValue(desc)?.ToString() ?? "";
                    var pNick = desc?.GetType().GetProperty("NickName")?.GetValue(desc)?.ToString() ?? "";
                    if (pName.ToLowerInvariant() == nameLower || pNick.ToLowerInvariant() == nameLower)
                    {
                        var compGuid = desc?.GetType().GetProperty("Guid")?.GetValue(desc)?.ToString() ?? "?";
                        var category = desc?.GetType().GetProperty("Category")?.GetValue(desc)?.ToString() ?? "";
                        var subcat = desc?.GetType().GetProperty("SubCategory")?.GetValue(desc)?.ToString() ?? "";
                        matches.Add((proxy, $"{pName} ({category}/{subcat}) GUID={compGuid}"));
                        if (matches.Count >= maxMatches)
                            break;
                    }
                }

                if (matches.Count == 0)
                    return (null, null, $"Component '{name}' not found");

                if (matches.Count > 1)
                    return (null, null, $"Ambiguous component name '{name}'. Use GUID instead. Matches: [{string.Join(", ", matches.Select(m => m.fullName))}]");

                component = matches[0].proxy.GetType().GetMethod("CreateInstance")?.Invoke(matches[0].proxy, null);
                if (component == null)
                    return (null, null, $"Component '{name}' found but CreateInstance returned null");
            }
            else
            {
                return (null, null, "Create entry needs 'type', 'guid', or 'name'");
            }

            // Set nickname if provided (for non-special types)
            if (specialType == null && item.TryGetProperty("nick", out var nickProp))
            {
                component!.GetType().GetProperty("NickName")?.SetValue(component, nickProp.GetString());
            }

            // Position and add to document
            var createAttrMethod = component!.GetType().GetMethod("CreateAttributes", BindingFlags.Public | BindingFlags.Instance);
            createAttrMethod?.Invoke(component, null);

            var attrP = component.GetType().GetProperty("Attributes");
            if (attrP != null)
            {
                var attr = attrP.GetValue(component);
                attr?.GetType().GetProperty("Pivot")?.SetValue(attr, new PointF(x, y));
            }

            var guidResult = AddObjectToDocument(gh.Document!, component);
            if (guidResult == null) return (null, null, "AddObjectToDocument returned null");

            var instanceGuid = (Guid)component.GetType().GetProperty("InstanceGuid")!.GetValue(component)!;
            return (instanceGuid, component, null);
        }

        /// <summary>
        /// Handle a single group operation from a batch edit.
        /// </summary>
        private void EditGroup(GrasshopperContext gh, JsonElement item, Dictionary<string, Guid> tempIdMap, object? undoUtil = null)
        {
            var action = item.TryGetProperty("action", out var actEl) ? actEl.GetString() : null;
            if (action == null) return;

            switch (action)
            {
                case "create":
                {
                    var groupType = gh.Assembly!.GetType("Grasshopper.Kernel.Special.GH_Group");
                    if (groupType == null) return;

                    var group = Activator.CreateInstance(groupType);
                    if (group == null) return;

                    if (item.TryGetProperty("nick", out var nickEl))
                        groupType.GetProperty("NickName")?.SetValue(group, nickEl.GetString());

                    if (item.TryGetProperty("colour", out var colEl))
                    {
                        var hex = colEl.GetString();
                        if (hex != null && hex.StartsWith("#") && hex.Length >= 7)
                        {
                            var r = Convert.ToInt32(hex.Substring(1, 2), 16);
                            var g2 = Convert.ToInt32(hex.Substring(3, 2), 16);
                            var b = Convert.ToInt32(hex.Substring(5, 2), 16);
                            // Support #RRGGBBAA format; default alpha=150 (GH group semi-transparency)
                            var a = hex.Length >= 9
                                ? Convert.ToInt32(hex.Substring(7, 2), 16)
                                : 150;
                            groupType.GetProperty("Colour")?.SetValue(group, Color.FromArgb(a, r, g2, b));
                        }
                    }
                    else
                    {
                        // Default: dark grey like a rook (semi-transparent)
                        groupType.GetProperty("Colour")?.SetValue(group, Color.FromArgb(150, 45, 45, 45));
                    }

                    // Create attributes
                    groupType.GetMethod("CreateAttributes", BindingFlags.Public | BindingFlags.Instance)?
                        .Invoke(group, null);

                    // Add members
                    if (item.TryGetProperty("members", out var membersEl) && membersEl.ValueKind == JsonValueKind.Array)
                    {
                        var addIdMethod = groupType.GetMethod("AddObject", new[] { typeof(Guid) });
                        foreach (var member in membersEl.EnumerateArray())
                        {
                            var memberId = member.GetString();
                            if (memberId == null) continue;
                            var memberGuid = ResolveEditId(memberId, tempIdMap);
                            if (memberGuid == null) continue;
                            addIdMethod?.Invoke(group, new object[] { memberGuid.Value });
                        }
                    }

                    AddObjectToDocument(gh.Document!, group!);
                    var groupGuid = (Guid)group!.GetType().GetProperty("InstanceGuid")!.GetValue(group)!;
                    _idRegistry.Register(groupGuid, isGroup: true);

                    // Record undo for group creation
                    if (undoUtil != null)
                    {
                        try { RecordUndoEvent(undoUtil, "Rook: create group", new List<object> { group }, isAdd: true); }
                        catch { /* undo recording is best-effort */ }
                    }
                    break;
                }
                case "delete":
                {
                    var id = item.TryGetProperty("id", out var idEl) ? idEl.GetString() : null;
                    if (id == null) return;
                    var guid = _idRegistry.Resolve(id);
                    if (guid == null) return;
                    var obj = FindObjectById(gh.Document!, guid.Value.ToString());
                    if (obj == null) return;

                    // Record undo BEFORE deletion
                    if (undoUtil != null)
                    {
                        try { RecordUndoEvent(undoUtil, "Rook: delete group", new List<object> { obj }, isAdd: false); }
                        catch { /* undo recording is best-effort */ }
                    }

                    var attrP = obj.GetType().GetProperty("Attributes")?.GetValue(obj);
                    if (attrP != null)
                    {
                        var removeMethod = gh.Document!.GetType().GetMethods()
                            .FirstOrDefault(m => m.Name == "RemoveObject" &&
                                m.GetParameters().Length == 2 &&
                                m.GetParameters()[1].ParameterType == typeof(bool));
                        removeMethod?.Invoke(gh.Document, new object[] { attrP, true });
                    }
                    break;
                }
                case "add_members":
                case "remove_members":
                {
                    var id = item.TryGetProperty("id", out var idEl) ? idEl.GetString() : null;
                    if (id == null) return;
                    var guid = _idRegistry.Resolve(id);
                    if (guid == null) return;
                    var groupObj = FindObjectById(gh.Document!, guid.Value.ToString());
                    if (groupObj == null) return;

                    // Record group state undo BEFORE membership change
                    if (undoUtil != null)
                    {
                        try { RecordGenericObjectUndoEvent(undoUtil, "Rook: modify group members", groupObj); }
                        catch { /* undo recording is best-effort */ }
                    }

                    var methodName = action == "add_members" ? "AddObject" : "RemoveObject";
                    var method = groupObj.GetType().GetMethod(methodName, new[] { typeof(Guid) });

                    if (item.TryGetProperty("members", out var membersEl) && membersEl.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var member in membersEl.EnumerateArray())
                        {
                            var memberId = member.GetString();
                            if (memberId == null) continue;
                            var memberGuid = ResolveEditId(memberId, tempIdMap);
                            if (memberGuid == null) continue;
                            method?.Invoke(groupObj, new object[] { memberGuid.Value });
                        }
                    }
                    break;
                }
            }
        }

        private object? BuildGroupEntry(object obj, string shortId)
        {
            try
            {
                var nick = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString();
                var description = obj.GetType().GetProperty("Description")?.GetValue(obj)?.ToString();

                // Get colour
                string? colourHex = null;
                var colour = obj.GetType().GetProperty("Colour")?.GetValue(obj);
                if (colour is Color c)
                    colourHex = c.A < 255
                        ? $"#{c.R:X2}{c.G:X2}{c.B:X2}{c.A:X2}"
                        : $"#{c.R:X2}{c.G:X2}{c.B:X2}";

                // Get member GUIDs and map to short IDs
                var memberShortIds = new List<string>();
                var objectIdsMethod = obj.GetType().GetMethod("ObjectIDs");
                if (objectIdsMethod != null)
                {
                    var ids = objectIdsMethod.Invoke(obj, null) as System.Collections.IEnumerable;
                    if (ids != null)
                    {
                        foreach (var id in ids)
                        {
                            if (id is Guid memberGuid)
                            {
                                var memberShortId = _idRegistry.ResolveReverse(memberGuid);
                                if (memberShortId != null)
                                    memberShortIds.Add(memberShortId);
                            }
                            else
                            {
                                // Try parsing string GUID
                                if (Guid.TryParse(id.ToString(), out var parsed))
                                {
                                    var memberShortId = _idRegistry.ResolveReverse(parsed);
                                    if (memberShortId != null)
                                        memberShortIds.Add(memberShortId);
                                }
                            }
                        }
                    }
                }
                else
                {
                    // Fallback: try Objects() method
                    var objectsMethod = obj.GetType().GetMethod("Objects");
                    if (objectsMethod != null)
                    {
                        var members = objectsMethod.Invoke(obj, null) as System.Collections.IEnumerable;
                        if (members != null)
                        {
                            foreach (var member in members)
                            {
                                var memberGuid = member.GetType().GetProperty("InstanceGuid")?
                                    .GetValue(member) as Guid?;
                                if (memberGuid.HasValue)
                                {
                                    var memberShortId = _idRegistry.ResolveReverse(memberGuid.Value);
                                    if (memberShortId != null)
                                        memberShortIds.Add(memberShortId);
                                }
                            }
                        }
                    }
                }

                return new
                {
                    id = shortId,
                    nick = nick,
                    description = string.IsNullOrWhiteSpace(description) ? null : description,
                    colour = colourHex,
                    members = memberShortIds
                };
            }
            catch { return null; }
        }

        #endregion

        #region Canvas Navigation

        /// <summary>
        /// POST /gh/canvas/focus - Zoom canvas to fit all objects or specific component IDs.
        /// Body: { ids?: string[], padding?: number }
        /// </summary>
        internal ApiResponse FocusCanvas(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_canvas_focus");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_canvas_focus", null, gh.Error);

            try
            {
                List<string>? ids = null;
                float padding = 20f;

                if (!string.IsNullOrEmpty(body))
                {
                    try
                    {
                        var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                        if (args != null)
                        {
                            if (args.TryGetValue("ids", out var idsEl) && idsEl.ValueKind == JsonValueKind.Array)
                                ids = idsEl.EnumerateArray().Select(e => e.GetString()!).ToList();
                            if (args.TryGetValue("padding", out var padEl))
                                padding = padEl.GetSingle();
                        }
                    }
                    catch { }
                }

                var viewportProp = gh.Canvas!.GetType().GetProperty("Viewport");
                var viewport = viewportProp?.GetValue(gh.Canvas);
                if (viewport == null)
                    return new ApiResponse { Success = false, Data = "Cannot access canvas viewport" };

                // Collect all document objects
                var objectsProp = gh.Document!.GetType().GetProperty("Objects");
                var allObjects = (objectsProp?.GetValue(gh.Document) as System.Collections.IEnumerable)?
                    .Cast<object>().ToList() ?? new List<object>();

                List<object> targetObjects;
                if (ids != null && ids.Count > 0)
                {
                    var targetGuids = new HashSet<string>();
                    foreach (var id in ids)
                    {
                        var resolved = _idRegistry.Resolve(id);
                        if (resolved.HasValue)
                            targetGuids.Add(resolved.Value.ToString());
                        else
                            targetGuids.Add(id);
                    }

                    targetObjects = allObjects.Where(obj =>
                    {
                        var guidProp = obj.GetType().GetProperty("InstanceGuid");
                        var objGuid = guidProp?.GetValue(obj)?.ToString();
                        return objGuid != null && targetGuids.Contains(objGuid);
                    }).ToList();
                }
                else
                {
                    targetObjects = allObjects;
                }

                if (targetObjects.Count == 0)
                    return new ApiResponse { Success = false, Data = "No objects found to focus on" };

                // Compute bounding envelope from Pivot points (document space)
                // Pivot is the only reliable document-space coordinate on IGH_Attributes.
                // Bounds is in screen space (transformed by current viewport) — not usable here.
                float minX = float.MaxValue, minY = float.MaxValue;
                float maxX = float.MinValue, maxY = float.MinValue;
                int collected = 0;
                foreach (var obj in targetObjects)
                {
                    var attrProp = obj.GetType().GetProperty("Attributes");
                    var attr = attrProp?.GetValue(obj);
                    if (attr == null) continue;

                    var pivotProp = attr.GetType().GetProperty("Pivot");
                    if (pivotProp == null) continue;
                    var pivot = pivotProp.GetValue(attr);
                    if (pivot is PointF pf)
                    {
                        if (pf.X < minX) minX = pf.X;
                        if (pf.Y < minY) minY = pf.Y;
                        if (pf.X > maxX) maxX = pf.X;
                        if (pf.Y > maxY) maxY = pf.Y;
                        collected++;
                    }
                }

                if (collected == 0)
                    return new ApiResponse { Success = false, Data = "No attributes with pivot found for target objects" };

                // Add padding for component sizes (pivots are top-left corners, components extend ~120x40)
                float compPadding = 80f + padding;
                minX -= compPadding;
                minY -= compPadding;
                maxX += compPadding;
                maxY += compPadding;

                float docWidth = maxX - minX;
                float docHeight = maxY - minY;

                // Step 1: Set zoom FIRST (zoom changes may reset MidPoint)
                var canvasSizeProp = gh.Canvas!.GetType().GetProperty("ClientSize");
                var clientSize = canvasSizeProp?.GetValue(gh.Canvas);
                var zoomProp = viewport.GetType().GetProperties()
                    .FirstOrDefault(p => p.Name == "Zoom" && p.GetIndexParameters().Length == 0);
                if (clientSize is Size cs && cs.Width > 0 && cs.Height > 0 && zoomProp != null && zoomProp.CanWrite)
                {
                    float zoomX = cs.Width / docWidth;
                    float zoomY = cs.Height / docHeight;
                    float fitZoom = Math.Min(zoomX, zoomY);
                    zoomProp.SetValue(viewport, fitZoom);
                }

                // Step 2: Force projection recomputation after zoom change
                var computeProjection = viewport.GetType().GetMethod("ComputeProjection");
                computeProjection?.Invoke(viewport, null);

                // Step 3: Set center AFTER zoom (MidPoint is in document space)
                var center = new PointF(minX + docWidth / 2f, minY + docHeight / 2f);
                var midPointProp = viewport.GetType().GetProperty("MidPoint");
                midPointProp?.SetValue(viewport, center);

                // Step 4: Recompute projection again and repaint
                computeProjection?.Invoke(viewport, null);
                RefreshCanvas(gh.Canvas);

                return new ApiResponse
                {
                    Success = true,
                    Data = new { focused = collected, total = targetObjects.Count }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"FocusCanvas failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /gh/canvas/zoom - Set zoom level and/or center point.
        /// Body: { zoom?: number, centerX?: number, centerY?: number }
        /// </summary>
        internal ApiResponse ZoomCanvas(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_canvas_zoom");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_canvas_zoom", null, gh.Error);

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Missing body parameters" };

            try
            {
                double? zoom = null;
                float? centerX = null;
                float? centerY = null;

                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args != null)
                {
                    if (args.TryGetValue("zoom", out var zoomEl))
                        zoom = zoomEl.GetDouble();
                    if (args.TryGetValue("centerX", out var cxEl))
                        centerX = cxEl.GetSingle();
                    if (args.TryGetValue("centerY", out var cyEl))
                        centerY = cyEl.GetSingle();
                }

                if (zoom == null && centerX == null && centerY == null)
                    return new ApiResponse { Success = false, Data = "Provide at least one of: zoom, centerX, centerY" };

                var viewportProp = gh.Canvas!.GetType().GetProperty("Viewport");
                var viewport = viewportProp?.GetValue(gh.Canvas);
                if (viewport == null)
                    return new ApiResponse { Success = false, Data = "Cannot access canvas viewport" };

                // Set Zoom — use parameterless property (not the indexed Zoom[Boolean])
                bool zoomApplied = false;
                if (zoom.HasValue)
                {
                    var zoomProps = viewport.GetType().GetProperties()
                        .Where(p => p.Name == "Zoom" && p.GetIndexParameters().Length == 0)
                        .ToList();
                    var zoomProp = zoomProps.FirstOrDefault();
                    if (zoomProp != null && zoomProp.CanWrite)
                    {
                        zoomProp.SetValue(viewport, (float)zoom.Value);
                        zoomApplied = true;
                    }
                }

                // Set MidPoint
                bool centerApplied = false;
                if (centerX.HasValue || centerY.HasValue)
                {
                    var midPointProp = viewport.GetType().GetProperty("MidPoint");
                    if (midPointProp != null)
                    {
                        var current = midPointProp.GetValue(viewport);
                        float cx = centerX ?? (current is PointF cp ? cp.X : 0);
                        float cy = centerY ?? (current is PointF cp2 ? cp2.Y : 0);
                        midPointProp.SetValue(viewport, new PointF(cx, cy));
                        centerApplied = true;
                    }
                }

                RefreshCanvas(gh.Canvas);

                // Read back final state
                var finalZoomProp = viewport.GetType().GetProperties()
                    .FirstOrDefault(p => p.Name == "Zoom" && p.GetIndexParameters().Length == 0);
                var finalMidProp = viewport.GetType().GetProperty("MidPoint");
                var finalZoom = finalZoomProp?.GetValue(viewport);
                var finalMid = finalMidProp?.GetValue(viewport);

                var warnings = new List<string>();
                if (zoom.HasValue && !zoomApplied) warnings.Add("Zoom property not found or not writable");
                if ((centerX.HasValue || centerY.HasValue) && !centerApplied) warnings.Add("MidPoint property not found");

                return new ApiResponse
                {
                    Success = true,
                    Data = new
                    {
                        zoom = finalZoom,
                        midPoint = finalMid is PointF mp ? new { x = mp.X, y = mp.Y } : null,
                        warnings = warnings.Count > 0 ? warnings : null
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"ZoomCanvas failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// GET /gh/canvas/image - Capture the canvas as a PNG image.
        /// Always saves to file, returns file path.
        /// </summary>
        internal ApiResponse CaptureCanvasImage(string? body)
        {
            var notReady = EnsureGrasshopperReadyForEdit("gh_canvas_image");
            if (notReady != null)
                return notReady;

            var gh = GetGrasshopper();
            if (!gh.Success)
                return GrasshopperNotReadyResponse("gh_canvas_image", null, gh.Error);

            try
            {
                // Get GH_CanvasMode.Export via reflection
                var canvasModeType = gh.Assembly!.GetType("Grasshopper.GUI.Canvas.GH_CanvasMode");
                if (canvasModeType == null)
                    return new ApiResponse { Success = false, Data = "GH_CanvasMode type not found" };

                object exportMode;
                try { exportMode = Enum.Parse(canvasModeType, "Export"); }
                catch (ArgumentException)
                {
                    return new ApiResponse { Success = false, Data = "GH_CanvasMode.Export not found — GH version may differ" };
                }

                // Call canvas.GetCanvasScreenBuffer(GH_CanvasMode.Export)
                var bufferMethod = gh.Canvas!.GetType().GetMethod("GetCanvasScreenBuffer",
                    new[] { canvasModeType });
                if (bufferMethod == null)
                    return new ApiResponse { Success = false, Data = "GetCanvasScreenBuffer method not found" };

                var bitmap = bufferMethod.Invoke(gh.Canvas, new[] { exportMode }) as Bitmap;
                if (bitmap == null)
                    return new ApiResponse { Success = false, Data = "Canvas capture returned null" };

                try
                {
                    var tempFolder = Path.Combine(Path.GetTempPath(), "rook", "gh");
                    Directory.CreateDirectory(tempFolder);
                    var timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss_fff");
                    var filePath = Path.Combine(tempFolder, $"canvas_{timestamp}.png");
                    bitmap.Save(filePath, ImageFormat.Png);

                    int width = bitmap.Width;
                    int height = bitmap.Height;

                    // Get visible region from viewport
                    object? visibleRegion = null;
                    var viewportProp = gh.Canvas.GetType().GetProperty("Viewport");
                    var viewport = viewportProp?.GetValue(gh.Canvas);
                    if (viewport != null)
                    {
                        var visRegionProp = viewport.GetType().GetProperty("VisibleRegion");
                        var vr = visRegionProp?.GetValue(viewport);
                        if (vr is Rectangle r)
                            visibleRegion = new { x = r.X, y = r.Y, width = r.Width, height = r.Height };
                        else if (vr is RectangleF rf)
                            visibleRegion = new { x = rf.X, y = rf.Y, width = rf.Width, height = rf.Height };
                    }

                    return new ApiResponse
                    {
                        Success = true,
                        Data = new Dictionary<string, object?>
                        {
                            ["filePath"] = filePath,
                            ["width"] = width,
                            ["height"] = height,
                            ["format"] = "png",
                            ["visibleRegion"] = visibleRegion,
                            ["message"] = "Canvas image saved. Use the Read tool to view the image."
                        }
                    };
                }
                finally
                {
                    bitmap.Dispose();
                }
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"CaptureCanvasImage failed: {ex.Message}" };
            }
        }

        #endregion
    }
}
